# Pydantic models matching Swift DTOs
from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from uuid import UUID, uuid4
from datetime import datetime
from typing import Optional


# ─── Enums ───────────────────────────────────────────────────────

class Industry(str, Enum):
    Q_healthcare = "Q - Gesundheitswesen"
    K_financialServices = "K - Finanzdienstleistungen"
    D_energy = "D - Energieversorgung"
    C_manufacturing = "C - Verarbeitendes Gewerbe"
    J_infoComm = "J - Information und Kommunikation"
    H_transport = "H - Verkehr und Lagerei"
    M_professional = "M - Freiberufliche Dienstleistungen"

    @property
    def short_name(self) -> str:
        return {
            "Q - Gesundheitswesen": "Healthcare",
            "K - Finanzdienstleistungen": "Financial Services",
            "D - Energieversorgung": "Energy",
            "C - Verarbeitendes Gewerbe": "Manufacturing",
            "J - Information und Kommunikation": "ICT",
            "H - Verkehr und Lagerei": "Transport & Logistics",
            "M - Freiberufliche Dienstleistungen": "Professional Services",
        }[self.value]

    @property
    def nace_section(self) -> str:
        return self.value.split(" ")[0]

    @property
    def key_regulations(self) -> str:
        return {
            "Q - Gesundheitswesen": "MDR, IVDR, GDPR/DSGVO, EU Health Data Space, NIS2",
            "K - Finanzdienstleistungen": "MiFID II, DORA, PSD2, AMLD6, Basel III/IV, DSGVO, ESG-Reporting",
            "D - Energieversorgung": "EU ETS, RED III, REMIT, NIS2, ESG, Energieeffizienzrichtlinie",
            "C - Verarbeitendes Gewerbe": "Maschinenverordnung, REACH, RoHS, CSRD, Lieferkettengesetz, ISO 27001",
            "J - Information und Kommunikation": "EU AI Act, NIS2, DSGVO, Digital Services Act, Data Act, Cyber Resilience Act",
            "H - Verkehr und Lagerei": "EU Mobility Package, NIS2, DSGVO, ADR/RID, EU ETS Seeverkehr",
            "M - Freiberufliche Dienstleistungen": "DSGVO, Geldwaeschegesetz, EU AI Act, Berufsrecht, CSRD",
        }[self.value]

    @property
    def search_terms(self) -> str:
        return {
            "Q - Gesundheitswesen": "healthcare, pharma, medical devices, biotech",
            "K - Finanzdienstleistungen": "banking, insurance, asset management, fintech",
            "D - Energieversorgung": "energy, utilities, renewables, solar, wind",
            "C - Verarbeitendes Gewerbe": "manufacturing, industrial, automotive, chemicals",
            "J - Information und Kommunikation": "software, IT services, telecommunications, cloud",
            "H - Verkehr und Lagerei": "logistics, transport, shipping, freight, warehousing",
            "M - Freiberufliche Dienstleistungen": "consulting, legal, accounting, engineering",
        }[self.value]


class Region(str, Enum):
    dach = "DACH"
    uk = "UK"
    baltics = "Baltics"
    nordics = "Nordics"
    benelux = "Benelux"
    france = "France"
    iberia = "Iberia"

    @property
    def countries(self) -> str:
        return {
            "DACH": "Germany, Austria, Switzerland",
            "UK": "United Kingdom",
            "Baltics": "Estonia, Latvia, Lithuania",
            "Nordics": "Sweden, Norway, Denmark, Finland",
            "Benelux": "Belgium, Netherlands, Luxembourg",
            "France": "France",
            "Iberia": "Spain, Portugal",
        }[self.value]


class CompanySize(str, Enum):
    small = "0-200 Mitarbeiter"
    medium = "201-5.000 Mitarbeiter"
    large = "5.001-500.000 Mitarbeiter"


class LeadStatus(str, Enum):
    identified = "Identified"
    email_verified = "Email Verified"
    followed_up = "Followed Up"
    qualified = "Qualified"
    converted = "Converted"
    not_interested = "Not Interested"
    email_approved = "Email Approved"
    email_drafted = "Email Drafted"
    email_sent = "Email Sent"
    follow_up_drafted = "Follow-Up Drafted"
    follow_up_sent = "Follow-Up Sent"
    replied = "Replied"
    do_not_contact = "Do Not Contact"
    closed = "Closed"


class DeliveryStatus(str, Enum):
    pending = "Pending"
    delivered = "Delivered"
    bounced = "Bounced"
    failed = "Failed"


class SocialPlatform(str, Enum):
    linkedin = "LinkedIn"
    twitter = "Twitter/X"


class ContentTopic(str, Enum):
    regulatory_update = "Regulatory Update"
    compliance_tip = "Compliance Tip"
    industry_insight = "Industry Insight"
    product_feature = "Product Feature"
    thought_leadership = "Thought Leadership"
    case_study = "Case Study"

    @property
    def prompt_prefix(self) -> str:
        return {
            "Regulatory Update": "Write about a recent regulatory change affecting",
            "Compliance Tip": "Share a practical compliance tip for",
            "Industry Insight": "Provide an industry insight about",
            "Product Feature": "Highlight a product feature relevant to",
            "Thought Leadership": "Share a thought leadership perspective on",
            "Case Study": "Present a case study about compliance in",
        }[self.value]


# ─── Database Models (SQLAlchemy in db.py, these are Pydantic schemas) ──

class CompanyBase(BaseModel):
    name: str
    industry: str = ""
    region: str = ""
    website: str = ""
    linkedin_url: str = ""
    description: str = ""
    size: str = ""
    country: str = ""
    nace_code: str = ""
    employee_count: int = 0


class CompanyCreate(CompanyBase):
    pass


class CompanyResponse(CompanyBase):
    id: UUID = Field(default_factory=uuid4)

    model_config = {"from_attributes": True}


class OutboundEmail(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    subject: str = ""
    body: str = ""
    is_approved: bool = False
    sent_date: Optional[datetime] = None


class LeadBase(BaseModel):
    name: str
    title: str = ""
    company: str = ""
    email: str = ""
    email_verified: bool = False
    linkedin_url: str = ""
    phone: str = ""
    responsibility: str = ""
    status: LeadStatus = LeadStatus.identified
    source: str = ""
    verification_notes: str = ""
    drafted_email: Optional[OutboundEmail] = None
    follow_up_email: Optional[OutboundEmail] = None
    date_identified: datetime = Field(default_factory=datetime.utcnow)
    date_email_sent: Optional[datetime] = None
    date_follow_up_sent: Optional[datetime] = None
    reply_received: str = ""
    is_manually_created: bool = False
    scheduled_send_date: Optional[datetime] = None
    opted_out: bool = False
    opt_out_date: Optional[datetime] = None
    delivery_status: DeliveryStatus = DeliveryStatus.pending


class LeadCreate(LeadBase):
    pass


class LeadResponse(LeadBase):
    id: UUID = Field(default_factory=uuid4)

    model_config = {"from_attributes": True}


class SocialPostBase(BaseModel):
    platform: SocialPlatform = SocialPlatform.linkedin
    content: str = ""
    hashtags: list[str] = Field(default_factory=list)
    created_date: datetime = Field(default_factory=datetime.utcnow)
    is_published: bool = False


class SocialPostCreate(SocialPostBase):
    pass


class SocialPostResponse(SocialPostBase):
    id: UUID = Field(default_factory=uuid4)

    model_config = {"from_attributes": True}


class BlocklistEntry(BaseModel):
    email: str
    reason: str = ""
    opted_out_at: datetime = Field(default_factory=datetime.utcnow)


# ─── API Request / Response DTOs ─────────────────────────────────

class SearchCompaniesRequest(BaseModel):
    industry: str
    region: str


class FindContactsRequest(BaseModel):
    company_id: UUID


class VerifyEmailRequest(BaseModel):
    lead_id: UUID


class DraftEmailRequest(BaseModel):
    lead_id: UUID
    is_follow_up: bool = False


class SendEmailRequest(BaseModel):
    lead_id: UUID
    subject: str = ""
    body: str = ""


class ApproveEmailRequest(BaseModel):
    lead_id: UUID


class GeneratePostRequest(BaseModel):
    topic: ContentTopic
    platform: SocialPlatform
    industries: list[str] = Field(default_factory=list)


class DashboardStats(BaseModel):
    total_leads: int = 0
    emails_sent: int = 0
    replies_received: int = 0
    conversion_rate: float = 0.0
    leads_by_status: dict[str, int] = Field(default_factory=dict)
    leads_by_industry: dict[str, int] = Field(default_factory=dict)


class APIResponse(BaseModel):
    success: bool
    data: Optional[dict | list] = None
    error: Optional[str] = None


class SettingsUpdate(BaseModel):
    perplexity_api_key: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    batch_size: Optional[int] = None
    selected_industries: Optional[list[str]] = None
    selected_regions: Optional[list[str]] = None
    selected_company_sizes: Optional[list[str]] = None

