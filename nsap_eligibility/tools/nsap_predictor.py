"""
NSAP Eligibility Predictor Tool
Uses IBM watsonx Granite-4 to predict the most appropriate NSAP scheme
for an applicant based on their demographic and socio-economic data.

Credentials are loaded from environment variables via python-dotenv.
Copy .env.example to .env and fill in your values before running.
"""

import json
import os
import requests
from typing import Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

# Load .env file if present (no-op in production where env vars are injected)
load_dotenv()

# ─── Configuration (from environment) ────────────────────────────────────────

def _require_env(key: str) -> str:
    """Return the value of an environment variable or raise a clear error."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy nsap_eligibility/.env.example to nsap_eligibility/.env and fill in your values."
        )
    return value


WATSONX_URL = os.getenv("WATSONX_AI_ENDPOINT",
                         "https://eu-de.ml.cloud.ibm.com/ml/v1/text/generation?version=2023-05-29")
MODEL_ID    = os.getenv("MODEL_ID", "ibm/granite-4-h-small")
IAM_URL     = "https://iam.cloud.ibm.com/identity/token"

NSAP_SCHEMES = {
    "IGNOAPS":      "Indira Gandhi National Old Age Pension Scheme",
    "IGNWPS":       "Indira Gandhi National Widow Pension Scheme",
    "IGNDPS":       "Indira Gandhi National Disability Pension Scheme",
    "NFBS":         "National Family Benefit Scheme",
    "NOT_ELIGIBLE": "Not Eligible for any NSAP scheme",
}

ELIGIBILITY_RULES = """
NSAP Scheme Eligibility Rules:
1. IGNOAPS (Old Age Pension): Age >= 60 years, BPL household, not receiving other pension.
2. IGNWPS (Widow Pension): Female, widowed, Age 40-79 years, BPL household.
3. IGNDPS (Disability Pension): Disability >= 80%, Age 18-79 years, BPL household.
4. NFBS (Family Benefit): Recent death of primary breadwinner (age 18-59), BPL household, one-time payment.
5. NOT_ELIGIBLE: Does not meet criteria for any of the above schemes.
"""


# ─── Models ───────────────────────────────────────────────────────────────────

class ApplicantInput(BaseModel):
    """Input data for NSAP scheme eligibility prediction."""
    applicant_name: str = Field(..., description="Full name of the applicant")
    age: int = Field(..., description="Age of the applicant in years", ge=0, le=120)
    gender: str = Field(..., description="Gender of the applicant: Male, Female, or Other")
    is_bpl: bool = Field(..., description="Whether the household is Below Poverty Line (BPL)")
    marital_status: str = Field(..., description="Marital status: Single, Married, Widowed, Divorced")
    disability_percentage: Optional[int] = Field(
        default=0,
        description="Percentage of disability (0-100). Use 0 if no disability.",
        ge=0, le=100
    )
    breadwinner_deceased: Optional[bool] = Field(
        default=False,
        description="Whether the primary breadwinner of the family has recently died"
    )
    breadwinner_age_at_death: Optional[int] = Field(
        default=None,
        description="Age of the deceased breadwinner at the time of death (if applicable)"
    )
    state: Optional[str] = Field(default="", description="State of the applicant in India")
    district: Optional[str] = Field(default="", description="District of the applicant")
    annual_income: Optional[float] = Field(
        default=0.0,
        description="Annual household income in INR"
    )
    existing_pension: Optional[bool] = Field(
        default=False,
        description="Whether the applicant is already receiving any government pension"
    )


class NSAPPredictionResult(BaseModel):
    """Result of NSAP scheme eligibility prediction."""
    applicant_name: str = Field(description="Name of the applicant")
    predicted_scheme: str = Field(description="Predicted NSAP scheme code (e.g., IGNOAPS)")
    scheme_full_name: str = Field(description="Full name of the predicted scheme")
    confidence: str = Field(description="Confidence level: High, Medium, or Low")
    eligibility_summary: str = Field(description="Brief explanation of why this scheme was predicted")
    monthly_benefit_inr: str = Field(description="Approximate monthly benefit amount in INR")
    next_steps: str = Field(description="Recommended next steps for the applicant")
    rule_based_prediction: str = Field(description="Rule-based prediction for cross-validation")


# ─── Helper Functions ──────────────────────────────────────────────────────────

def _get_iam_token() -> str:
    """Fetch IBM IAM bearer token using API key from environment."""
    api_key = _require_env("IBM_CLOUD_API_KEY")
    response = requests.post(
        IAM_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _rule_based_predict(applicant: ApplicantInput) -> str:
    """
    Deterministic rule-based NSAP scheme prediction.
    Used as fallback and cross-validation against LLM prediction.
    """
    if not applicant.is_bpl:
        return "NOT_ELIGIBLE"

    # NFBS: breadwinner died between age 18-59
    if (
        applicant.breadwinner_deceased
        and applicant.breadwinner_age_at_death is not None
        and 18 <= applicant.breadwinner_age_at_death <= 59
    ):
        return "NFBS"

    # IGNDPS: disability >= 80%, age 18-79
    if (
        applicant.disability_percentage
        and applicant.disability_percentage >= 80
        and 18 <= applicant.age <= 79
    ):
        return "IGNDPS"

    # IGNWPS: widowed female, age 40-79
    if (
        applicant.gender.lower() in ["female", "f"]
        and applicant.marital_status.lower() == "widowed"
        and 40 <= applicant.age <= 79
    ):
        return "IGNWPS"

    # IGNOAPS: age >= 60, not already on pension
    if applicant.age >= 60 and not applicant.existing_pension:
        return "IGNOAPS"

    return "NOT_ELIGIBLE"


def _get_benefit_amount(scheme: str) -> str:
    """Return approximate monthly benefit amount for each scheme."""
    benefits = {
        "IGNOAPS":      "Rs.200-500/month (Centre) + State top-up",
        "IGNWPS":       "Rs.300/month (Centre) + State top-up",
        "IGNDPS":       "Rs.300/month (Centre) + State top-up",
        "NFBS":         "Rs.20,000 one-time payment",
        "NOT_ELIGIBLE": "N/A",
    }
    return benefits.get(scheme, "N/A")


def _get_next_steps(scheme: str) -> str:
    """Return next steps for the applicant based on predicted scheme."""
    steps = {
        "IGNOAPS": (
            "Visit your local Gram Panchayat/Block Development Office with Aadhaar, "
            "BPL certificate, age proof, and bank passbook to apply for IGNOAPS."
        ),
        "IGNWPS": (
            "Visit your local Gram Panchayat/Block Development Office with Aadhaar, "
            "BPL certificate, death certificate of spouse, age proof, and bank passbook "
            "to apply for IGNWPS."
        ),
        "IGNDPS": (
            "Visit your local Gram Panchayat/Block Development Office with Aadhaar, "
            "BPL certificate, disability certificate (80%+), age proof, and bank passbook "
            "to apply for IGNDPS."
        ),
        "NFBS": (
            "Visit your local Gram Panchayat/Block Development Office within 90 days of "
            "breadwinner's death with Aadhaar, BPL certificate, death certificate, and "
            "bank passbook to apply for NFBS."
        ),
        "NOT_ELIGIBLE": (
            "The applicant does not meet current NSAP eligibility criteria. "
            "Consider applying for state-level schemes or MGNREGS for employment support."
        ),
    }
    return steps.get(scheme, "Contact your local district welfare office for guidance.")


def _call_watsonx(prompt: str, token: str) -> str:
    """Call IBM watsonx Granite text generation API."""
    project_id = _require_env("PROJECT_ID")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model_id": MODEL_ID,
        "project_id": project_id,
        "input": prompt,
        "parameters": {
            "decoding_method": "greedy",
            "max_new_tokens": 300,
            "min_new_tokens": 10,
            "stop_sequences": ["###"],
            "temperature": 0.1,
        },
    }
    response = requests.post(WATSONX_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    return result.get("results", [{}])[0].get("generated_text", "").strip()


def _build_prompt(applicant: ApplicantInput, rule_prediction: str) -> str:
    """Build the classification prompt for watsonx Granite."""
    return f"""You are an NSAP (National Social Assistance Program) eligibility expert for the Government of India.

{ELIGIBILITY_RULES}

Applicant Profile:
- Name: {applicant.applicant_name}
- Age: {applicant.age} years
- Gender: {applicant.gender}
- BPL Household: {"Yes" if applicant.is_bpl else "No"}
- Marital Status: {applicant.marital_status}
- Disability: {applicant.disability_percentage}%
- Breadwinner Deceased: {"Yes" if applicant.breadwinner_deceased else "No"}
- Breadwinner Age at Death: {applicant.breadwinner_age_at_death if applicant.breadwinner_age_at_death else "N/A"}
- State: {applicant.state or "Not specified"}
- District: {applicant.district or "Not specified"}
- Annual Income: Rs.{applicant.annual_income:,.0f}
- Existing Pension: {"Yes" if applicant.existing_pension else "No"}
- Rule-Based Prediction: {rule_prediction}

Based on the eligibility rules and applicant profile, respond ONLY with a JSON object in this exact format:
{{
  "predicted_scheme": "<one of: IGNOAPS, IGNWPS, IGNDPS, NFBS, NOT_ELIGIBLE>",
  "confidence": "<one of: High, Medium, Low>",
  "eligibility_summary": "<2-3 sentence explanation of why this scheme was chosen>"
}}
###"""


# ─── Main Tool ────────────────────────────────────────────────────────────────

@tool(permission=ToolPermission.READ_ONLY)
def predict_nsap_scheme(applicant: ApplicantInput) -> NSAPPredictionResult:
    """
    Predict the most appropriate NSAP scheme for an applicant using IBM watsonx Granite.

    Uses a hybrid approach: rule-based prediction for reliability combined with
    IBM watsonx Granite LLM for intelligent multi-class classification.
    Covers IGNOAPS (old age), IGNWPS (widow), IGNDPS (disability), NFBS (family benefit).
    Credentials are read from environment variables — no secrets are hardcoded.

    Args:
        applicant (ApplicantInput): Demographic and socio-economic data of the applicant

    Returns:
        NSAPPredictionResult: Predicted NSAP scheme with explanation, benefits, and next steps
    """
    # Step 1: Fast deterministic rule-based prediction
    rule_pred = _rule_based_predict(applicant)

    # Step 2: IBM watsonx Granite LLM classification
    try:
        token = _get_iam_token()
        prompt = _build_prompt(applicant, rule_pred)
        llm_response = _call_watsonx(prompt, token)

        json_start = llm_response.find("{")
        json_end = llm_response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            llm_data = json.loads(llm_response[json_start:json_end])
            predicted_scheme = llm_data.get("predicted_scheme", rule_pred)
            confidence = llm_data.get("confidence", "Medium")
            eligibility_summary = llm_data.get("eligibility_summary", "")
        else:
            predicted_scheme = rule_pred
            confidence = "High"
            eligibility_summary = (
                f"Predicted using rule-based classification: {NSAP_SCHEMES.get(rule_pred, '')}"
            )

    except EnvironmentError:
        # Re-raise config errors so they surface clearly
        raise
    except Exception:
        # Fallback to rule-based if watsonx call fails
        predicted_scheme = rule_pred
        confidence = "High"
        eligibility_summary = (
            f"Predicted using rule-based classification: {NSAP_SCHEMES.get(rule_pred, '')}"
        )

    return NSAPPredictionResult(
        applicant_name=applicant.applicant_name,
        predicted_scheme=predicted_scheme,
        scheme_full_name=NSAP_SCHEMES.get(predicted_scheme, "Unknown"),
        confidence=confidence,
        eligibility_summary=eligibility_summary,
        monthly_benefit_inr=_get_benefit_amount(predicted_scheme),
        next_steps=_get_next_steps(predicted_scheme),
        rule_based_prediction=rule_pred,
    )
