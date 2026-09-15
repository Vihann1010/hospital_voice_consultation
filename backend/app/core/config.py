"""Central application configuration.

Every tunable of the platform is sourced from environment variables so the
same image can be promoted across environments without a rebuild.
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application -------------------------------------------------------
    APP_NAME: str = "Satya Hospital AI Platform"
    APP_ENV: str = "production"  # production | staging | development
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # json: one object per line, for log shipping. pretty: readable lines, for local debugging.
    LOG_FORMAT: str = "json"
    # One line per HTTP request: method, path, status, duration and who made it.
    LOG_REQUESTS: bool = True
    CORS_ORIGINS: str = "http://localhost:3000"

    # --- Database ----------------------------------------------------------
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "satya"
    POSTGRES_PASSWORD: str = "satya"
    POSTGRES_DB: str = "satya_hospital"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Security ----------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8          # staff sessions
    # A QR code on a screen in a shared room can be photographed by whoever
    # is next in the queue, so the token behind it is deliberately brief.
    UPLOAD_TOKEN_EXPIRE_MINUTES: int = 15
    CONSULTATION_TOKEN_EXPIRE_MINUTES: int = 120        # patient voice sessions
    FINANCE_PIN: str = "4827"

    # --- Seed users (created on first boot) --------------------------------
    ADMIN_EMAIL: str = "admin@satyahospital.in"
    ADMIN_PASSWORD: str = "ChangeMe@123"
    DR_AK_AGARWAL_EMAIL: str = "ak.agarwal@satyahospital.in"
    DR_AK_AGARWAL_PASSWORD: str = "ChangeMe@123"
    DR_MANISHA_AGARWAL_EMAIL: str = "manisha.agarwal@satyahospital.in"
    DR_MANISHA_AGARWAL_PASSWORD: str = "ChangeMe@123"

    # --- Sarvam AI (speech) -------------------------------------------------
    SARVAM_API_KEY: str = ""
    SARVAM_STT_WS_URL: str = "wss://api.sarvam.ai/speech-to-text/ws"
    SARVAM_STT_MODEL: str = "saaras:v3"
    SARVAM_STT_LANGUAGE: str = "hi-IN"
    SARVAM_STT_MODE: str = "codemix"
    SARVAM_TTS_WS_URL: str = "wss://api.sarvam.ai/text-to-speech/ws"
    SARVAM_TTS_MODEL: str = "bulbul:v2"
    SARVAM_TTS_SPEAKER: str = "anushka"
    SARVAM_TTS_LANGUAGE: str = "en-IN"
    SARVAM_TTS_SAMPLE_RATE: int = 22050
    INPUT_AUDIO_SAMPLE_RATE: int = 16000

    # --- LLM provider (fully switchable) ------------------------------------
    # LLM_PROVIDER: "sarvam" | "openai" | "anthropic" | "custom"
    #   sarvam/openai/custom -> any OpenAI-compatible /chat/completions endpoint
    #   anthropic            -> Anthropic Messages API
    LLM_PROVIDER: str = "sarvam"
    LLM_BASE_URL: str = "https://api.sarvam.ai/v1"
    LLM_API_KEY: str = ""                               # falls back to SARVAM_API_KEY
    LLM_MODEL: str = "sarvam-m"                         # dialogue tier
    LLM_FAST_MODEL: str = ""                            # cheap tier; falls back to LLM_MODEL
    LLM_SUPPORTS_JSON_MODE: bool = False                # response_format json_object support
    ANTHROPIC_VERSION: str = "2023-06-01"
    # Lower than a chat default: the assistant should ask a clear question the
    # same way every time, not improvise.
    LLM_TEMPERATURE: float = 0.35
    # Shared between the spoken utterance and the JSON keys that follow it.
    # Devanagari costs two to three tokens per word, so a tight budget was
    # cutting replies off mid-sentence before the object closed.
    LLM_MAX_TOKENS: int = 700
    EXTRACTION_LLM_MAX_TOKENS: int = 1200

    # --- LLM resilience ------------------------------------------------------
    LLM_REQUEST_TIMEOUT_S: float = 45.0
    LLM_CONNECT_TIMEOUT_S: float = 10.0
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_BASE_DELAY_S: float = 0.5
    LLM_RETRY_MAX_DELAY_S: float = 8.0

    # --- LLM response cache --------------------------------------------------
    AI_CACHE_ENABLED: bool = True
    AI_CACHE_TTL_S: int = 3600
    AI_CACHE_MAX_ENTRIES: int = 512

    # --- Cost tracking (per 1M tokens; 0 disables cost math) -----------------
    LLM_INPUT_COST_PER_MTOK: float = 0.0
    LLM_OUTPUT_COST_PER_MTOK: float = 0.0

    # --- Echo rejection --------------------------------------------------------
    # The microphone keeps streaming while the assistant talks, so on device
    # speakers some of its own audio is recognised as patient speech. Left
    # alone this cancels replies mid-sentence and files the assistant's words
    # as patient turns.
    ECHO_REJECTION_ENABLED: bool = True
    # Half-duplex: while the assistant is speaking (and briefly after), the
    # microphone is not forwarded to speech recognition at all.
    #
    # Text-based echo detection cannot save us on its own. When the assistant's
    # Hindi audio leaks into the microphone, recognition running in
    # auto-detect mode frequently returns English gibberish — one real example
    # was "Recognize a little anything and alcoholism." Nothing in that string
    # resembles what the assistant actually said, so it is scored as genuine
    # speech, cancels the reply mid-sentence, and is filed as a patient turn.
    #
    # Not sending the audio at all removes the failure at its source: no audio
    # in, no transcript, no false interruption. The cost is that the patient
    # cannot cut the assistant off while it is talking. Since replies here are
    # one or two short sentences, that is a good trade — and it is a setting,
    # so it can be turned off if genuine barge-in ever matters more.
    HALF_DUPLEX_ENABLED: bool = True
    # Speech recognised within this window of the assistant starting to talk
    # does not interrupt it: the opening words are the most likely to echo.
    BARGE_IN_GRACE_S: float = 1.5
    # Recognition finalises an utterance shortly after audio ends, so keep
    # comparing against the assistant's words for this long after it stops.
    ECHO_TAIL_S: float = 2.0

    # --- Opening greeting ------------------------------------------------------
    # Spoken the moment the call connects, before any model is involved. Fixed
    # rather than generated so the patient is always greeted instantly, even if
    # the LLM is rate limited or unavailable — and so the first thing a patient
    # hears is wording the hospital controls, not model output.
    GREETING_ENABLED: bool = True
    GREETING_TEXT: str = (
        "नमस्ते, मैं नेहा बोल रही हूँ, सत्या हॉस्पिटल की A I सहायिका। "
        "डॉक्टर साहब से मिलने से पहले मैं आपकी तकलीफ़ समझना चाहती हूँ। "
        "बताइए, आपको क्या तकलीफ़ हो रही है?"
    )

    # --- Conversation / pipeline behaviour -----------------------------------
    MAX_PATIENT_TURNS: int = 8             # hard ceiling before wrap-up
    MEDICAL_JSON_EVERY_N_TURNS: int = 3    # mid-session regeneration cadence
    MEMORY_VERBATIM_TURNS: int = 16        # rolling verbatim window; older turns live in the fact digest

    # --- Media / recording ----------------------------------------------------
    MEDIA_ROOT: str = "/data/media"

    # --- Report extraction / OCR ----------------------------------------------
    OCR_LANGUAGES: str = "eng"          # e.g. "eng+hin" once the hin pack is installed
    OCR_DPI: int = 300
    OCR_MAX_PAGES: int = 12
    MAX_REPORT_UPLOAD_MB: int = 25

    # --- Hospital -----------------------------------------------------------
    # The wall clock the hospital runs on. Timestamps are stored in UTC, but
    # "today" and "nine o'clock" have to mean what they mean in Kanpur: with
    # the server on UTC, a visit registered at 05:00 IST would otherwise be
    # dated to the previous day, and a 09:00 appointment slot would be
    # offered for the middle of the night.
    HOSPITAL_TIMEZONE: str = "Asia/Kolkata"

    # --- Prescriptions ---------------------------------------------------------
    HOSPITAL_NAME: str = "Satya Trauma & Maternity Center"
    HOSPITAL_CITY: str = "Kanpur, Uttar Pradesh"
    PRESCRIPTION_NUMBER_PREFIX: str = "ST"
    # Public origin used for QR verification links and signed document URLs.
    PUBLIC_BASE_URL: str = "http://localhost:3000"
    DOCUMENT_LINK_TTL_S: int = 172800          # signed links live 48 hours

    # --- Messaging -------------------------------------------------------------
    # console | whatsapp_cloud | twilio
    MESSAGING_PROVIDER: str = "console"
    MESSAGING_TIMEOUT_S: float = 30.0
    MESSAGING_MAX_ATTEMPTS: int = 5
    MESSAGING_RETRY_BASE_S: float = 30.0
    MESSAGING_RETRY_MAX_S: float = 3600.0
    MESSAGING_SWEEP_INTERVAL_S: int = 60
    DEFAULT_COUNTRY_CODE: str = "91"

    WHATSAPP_API_BASE: str = "https://graph.facebook.com/v21.0"
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""

    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = ""

    # --- Rate limiting ---------------------------------------------------------
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT_PER_MIN: int = 240
    RATE_LIMIT_AUTH_PER_MIN: int = 10
    RATE_LIMIT_INTAKE_PER_MIN: int = 20
    RATE_LIMIT_UPLOAD_PER_MIN: int = 30
    RATE_LIMIT_PUBLIC_PER_MIN: int = 60

    # --- Observability ---------------------------------------------------------
    AUDIT_ENABLED: bool = True
    METRICS_ENABLED: bool = True
    REQUEST_ID_HEADER: str = "X-Request-ID"
    SHUTDOWN_GRACE_S: float = 20.0

    # Room charges are posted each morning after the census hour (08:00),
    # when the day's bed is decided. See app/ipd/room_charges.py.
    BED_CHARGE_WORKER_ENABLED: bool = True
    BED_CHARGE_RUN_AT: str = "08:30"
    BED_CHARGE_CHECK_S: float = 300.0
    # The go-live date (YYYY-MM-DD). Bed and nursing days before it are never
    # posted, so an admission already in a bed is not back-billed.
    BED_CHARGE_POST_FROM: str = ""

    # The books follow the counter: new and changed bills, receipts and
    # advances are posted this often. See app/accounts/worker.py.
    BOOKS_POSTING_ENABLED: bool = True
    BOOKS_POSTING_INTERVAL_S: float = 600.0

    # The kitchen sheet serves each meal against the diet order in effect at
    # that meal's time, in hospital time. Label=HH:MM, in the order served.
    DIET_MEAL_TIMES: str = "Breakfast=08:00,Lunch=13:00,Dinner=20:00"

    # --- Session management ---------------------------------------------------
    SESSION_IDLE_TTL_S: int = 1800
    SESSION_REAPER_INTERVAL_S: int = 300
    MAX_ACTIVE_SESSIONS: int = 200

    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("FINANCE_PIN")
    @classmethod
    def _finance_pin_must_be_four_digits(cls, v: str) -> str:
        if len(v) != 4 or not v.isdigit():
            raise ValueError("FINANCE_PIN must contain exactly four digits")
        return v

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def llm_api_key(self) -> str:
        return self.LLM_API_KEY or self.SARVAM_API_KEY

    @property
    def llm_fast_model(self) -> str:
        return self.LLM_FAST_MODEL or self.LLM_MODEL


INSECURE_DEFAULTS = {
    "JWT_SECRET_KEY": "change-me-in-production",
    "ADMIN_PASSWORD": "ChangeMe@123",
    "DR_AK_AGARWAL_PASSWORD": "ChangeMe@123",
    "DR_MANISHA_AGARWAL_PASSWORD": "ChangeMe@123",
    "POSTGRES_PASSWORD": "satya",
}


class InsecureConfigurationError(RuntimeError):
    """Raised when production would boot with shipped default credentials."""


def assert_production_ready(config: "Settings") -> None:
    """Refuse to start production with the values from .env.example.

    A hospital deployment that boots with a known JWT secret is a deployment
    anyone can mint tokens for. Failing loudly at startup is far better than
    discovering this later.
    """
    if config.APP_ENV.lower() not in {"production", "prod"}:
        return
    problems = [
        f"{name} is still the shipped default"
        for name, insecure in INSECURE_DEFAULTS.items()
        if getattr(config, name, None) == insecure
    ]
    if len(config.JWT_SECRET_KEY) < 32:
        problems.append("JWT_SECRET_KEY must be at least 32 characters")
    if config.DEBUG:
        problems.append("DEBUG must be false in production")
    if "*" in config.cors_origins_list:
        problems.append("CORS_ORIGINS must not be a wildcard in production")
    if problems:
        raise InsecureConfigurationError(
            "Refusing to start in production with insecure configuration:\n  - "
            + "\n  - ".join(problems)
            + "\n\nGenerate a secret with: openssl rand -hex 32"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
