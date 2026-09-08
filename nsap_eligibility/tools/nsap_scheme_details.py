"""
NSAP District Statistics Tool
Provides district-level NSAP scheme distribution statistics and analytics.

Credentials are loaded from environment variables via python-dotenv.
Copy .env.example to .env and fill in your values before running.
"""

import os
from typing import List, Any, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission

# Load .env file if present
load_dotenv()

# Application portal sourced from env with sensible default
NSAP_PORTAL = os.getenv("NSAP_PORTAL_URL", "https://nsap.nic.in")


class DistrictStatsInput(BaseModel):
    """Input for district-level NSAP statistics."""
    state_name: str = Field(..., description="Name of the Indian state")
    district_name: Optional[str] = Field(
        default=None,
        description="Name of the district (optional; if omitted, returns state-level stats)"
    )


class SchemeStats(BaseModel):
    """Statistics for a single NSAP scheme."""
    scheme_code: str = Field(description="NSAP scheme code")
    scheme_name: str = Field(description="Full scheme name")
    beneficiary_description: str = Field(description="Who this scheme covers")
    central_amount_inr: str = Field(description="Central government contribution per month")
    eligibility_criteria: str = Field(description="Key eligibility criteria")


class DistrictStatsResult(BaseModel):
    """District/state level NSAP scheme statistics."""
    location: str = Field(description="State or State/District queried")
    schemes: List[SchemeStats] = Field(description="List of NSAP schemes with details")
    general_notes: str = Field(description="General notes about NSAP in this region")
    application_portal: str = Field(description="Online application portal URL")


SCHEME_DATA = [
    SchemeStats(
        scheme_code="IGNOAPS",
        scheme_name="Indira Gandhi National Old Age Pension Scheme",
        beneficiary_description="BPL elderly citizens aged 60 years and above",
        central_amount_inr="₹200/month (age 60-79), ₹500/month (age 80+)",
        eligibility_criteria="Age >= 60 years, BPL household, not receiving any other pension from Central/State govt"
    ),
    SchemeStats(
        scheme_code="IGNWPS",
        scheme_name="Indira Gandhi National Widow Pension Scheme",
        beneficiary_description="BPL widows aged 40 to 79 years",
        central_amount_inr="₹300/month",
        eligibility_criteria="Female, widowed, age 40-79 years, BPL household"
    ),
    SchemeStats(
        scheme_code="IGNDPS",
        scheme_name="Indira Gandhi National Disability Pension Scheme",
        beneficiary_description="BPL persons with severe or multiple disabilities aged 18-79",
        central_amount_inr="₹300/month",
        eligibility_criteria="Disability >= 80%, age 18-79 years, BPL household"
    ),
    SchemeStats(
        scheme_code="NFBS",
        scheme_name="National Family Benefit Scheme",
        beneficiary_description="BPL households that have lost their primary breadwinner",
        central_amount_inr="₹20,000 one-time lump sum",
        eligibility_criteria="Breadwinner's death aged 18-59 years, BPL household, applied within 90 days of death"
    )
]


@tool(permission=ToolPermission.READ_ONLY)
def get_nsap_scheme_details(query: DistrictStatsInput) -> DistrictStatsResult:
    """
    Get detailed information about NSAP schemes available in a specific state or district.

    Returns all four NSAP sub-schemes with eligibility criteria, benefit amounts,
    and application guidance relevant to the queried location.

    Args:
        query (DistrictStatsInput): State and optional district name to query

    Returns:
        DistrictStatsResult: NSAP scheme details and application information for the region
    """
    location = query.state_name
    if query.district_name:
        location = f"{query.district_name}, {query.state_name}"

    return DistrictStatsResult(
        location=location,
        schemes=SCHEME_DATA,
        general_notes=(
            f"In {query.state_name}, the State Government may provide additional top-up amounts "
            "over and above the central contribution. Contact your local District Social Welfare "
            "Officer or Gram Panchayat for state-specific benefit amounts. Applications are "
            "processed through the National Social Assistance Programme Management Information "
            "System (NSAP-MIS)."
        ),
        application_portal=NSAP_PORTAL
    )
