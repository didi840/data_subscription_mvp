import re
import base64
import os
import uuid
import hashlib
import hmac
import secrets
import requests
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from functools import wraps
from datetime import datetime,timedelta

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes,
)
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")
print("Brevo API key loaded:", bool(os.getenv("BREVO_API_KEY")))
print("Brevo sender email loaded:", bool(os.getenv("BREVO_SENDER_EMAIL")))
print("MongoDB URI loaded:", bool(os.getenv("MONGO_URI")))
def send_verification_email(recipient_email, verification_code):
    """
    Send an email verification code through Brevo.
    Returns True if Brevo accepts the email, otherwise False.
    """

    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")

    if not api_key or not sender_email:
        app.logger.error(
            "Brevo configuration is missing. "
            "Check BREVO_API_KEY and BREVO_SENDER_EMAIL in your .env file."
        )
        return False

    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    payload = {
        "sender": {
            "name": "DataHub",
            "email": sender_email
        },
        "to": [
            {
                "email": recipient_email
            }
        ],
        "subject": "Your DataHub Email Verification Code",
        "htmlContent": f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:30px;background:#f4f4f4;
                     font-family:Arial,sans-serif;">
            <div style="max-width:500px;margin:auto;background:#ffffff;
                        padding:30px;border-radius:12px;">
                <h2 style="color:#111827;">Welcome to DataHub!</h2>

                <p style="color:#4b5563;">
                    Use the verification code below to verify your email
                    address and complete your registration.
                </p>

                <div style="background:#fff8d6;border:1px solid #ffd400;
                            padding:20px;text-align:center;
                            border-radius:10px;margin:25px 0;">
                    <h1 style="color:#111827;letter-spacing:8px;
                               margin:0;">
                        {verification_code}
                    </h1>
                </div>

                <p style="color:#4b5563;">
                    This code expires in 10 minutes. Do not share it
                    with anyone.
                </p>

                <p style="color:#6b7280;font-size:12px;">
                    If you did not request this code, you can ignore
                    this email.
                </p>
            </div>
        </body>
        </html>
        """
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=20
        )

        if response.status_code in (200, 201, 202):
            app.logger.info(
                "Verification email accepted by Brevo for %s",
                recipient_email
            )
            return True

        app.logger.error(
            "Brevo email failed. Status: %s. Response: %s",
            response.status_code,
            response.text
        )
        return False

    except requests.RequestException:
        app.logger.exception(
            "Could not connect to Brevo while sending verification email."
        )
        return False

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key-change-this"
)
# ==========================================
# BREVO EMAIL VERIFICATION CONFIGURATION
# ==========================================

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()

BREVO_SENDER_EMAIL = os.getenv(
    "BREVO_SENDER_EMAIL", ""
).strip()

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

# =========================================================
# MONGODB CONNECTION
# =========================================================

MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://Data_subscription_app:<YOUR_PASSWORD>@cluster0.j75bqur.mongodb.net/?appName=Cluster0"
)

client = MongoClient(MONGO_URI)

db = client["student_management"] if False else client["data_subscription"]


# =========================================================
# WEBAUTHN / FINGERPRINT LOGIN
# =========================================================

WEBAUTHN_RP_ID = "127.0.0.1"

WEBAUTHN_RP_NAME = "DataHub"

WEBAUTHN_ORIGIN = "http://127.0.0.1:5002"


# =========================================================
# COLLECTIONS
# =========================================================

users = db["users"]

plans = db["data_plans"]

transactions = db["transactions"]

webauthn_credentials = db["webauthn_credentials"]

pending_registrations = db["pending_registrations"]
password_resets = db["password_resets"]
# =========================================================
# DATABASE HELPERS
# =========================================================

def seed_plans():

    # -----------------------------------------------------
    # EXISTING GIFTING PLANS
    # -----------------------------------------------------

    gifting_plans = [

        {
            "network": "MTN",
            "type": "Gifting",
            "name": "1GB",
            "price": 500,
            "duration": "1 Day",
            "active": True
        },

        {
            "network": "MTN",
            "type": "Gifting",
            "name": "2GB",
            "price": 900,
            "duration": "3 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "Gifting",
            "name": "5GB",
            "price": 2000,
            "duration": "1 Week",
            "active": True
        },

        {
            "network": "Airtel",
            "type": "Gifting",
            "name": "1GB",
            "price": 500,
            "duration": "1 Day",
            "active": True
        },

        {
            "network": "Airtel",
            "type": "Gifting",
            "name": "2GB",
            "price": 900,
            "duration": "3 Days",
            "active": True
        },

        {
            "network": "Airtel",
            "type": "Gifting",
            "name": "5GB",
            "price": 2000,
            "duration": "1 Week",
            "active": True
        },

        {
            "network": "Glo",
            "type": "Gifting",
            "name": "1GB",
            "price": 450,
            "duration": "1 Day",
            "active": True
        },

        {
            "network": "Glo",
            "type": "Gifting",
            "name": "2GB",
            "price": 850,
            "duration": "3 Days",
            "active": True
        },

        {
            "network": "Glo",
            "type": "Gifting",
            "name": "5GB",
            "price": 1900,
            "duration": "1 Week",
            "active": True
        },

        {
            "network": "9mobile",
            "type": "Gifting",
            "name": "1GB",
            "price": 500,
            "duration": "1 Day",
            "active": True
        },

        {
            "network": "9mobile",
            "type": "Gifting",
            "name": "2GB",
            "price": 900,
            "duration": "3 Days",
            "active": True
        },

        {
            "network": "9mobile",
            "type": "Gifting",
            "name": "5GB",
            "price": 2000,
            "duration": "1 Week",
            "active": True
        }
    ]


    for plan in gifting_plans:

        plans.update_one(
            {
                "network": plan["network"],
                "type": plan["type"],
                "name": plan["name"],
                "duration": plan["duration"]
            },

            {
                "$set": {
                    "price": plan["price"],
                    "active": plan["active"]
                }
            },

            upsert=True
        )


    # -----------------------------------------------------
    # FIX OLD PLANS THAT DON'T HAVE DURATION
    # -----------------------------------------------------

    plans.update_many(
        {
            "duration": {
                "$exists": False
            },
            "name": "1GB"
        },

        {
            "$set": {
                "duration": "1 Day"
            }
        }
    )


    plans.update_many(
        {
            "duration": {
                "$exists": False
            },
            "name": "2GB"
        },

        {
            "$set": {
                "duration": "3 Days"
            }
        }
    )


    plans.update_many(
        {
            "duration": {
                "$exists": False
            },
            "name": "5GB"
        },

        {
            "$set": {
                "duration": "1 Week"
            }
        }
    )


    # -----------------------------------------------------
    # FIX OLD PLANS THAT DON'T HAVE TYPE
    # -----------------------------------------------------

    plans.update_many(
        {
            "type": {
                "$exists": False
            }
        },

        {
            "$set": {
                "type": "Gifting"
            }
        }
    )


    # -----------------------------------------------------
    # MTN SME PLANS
    # -----------------------------------------------------

    mtn_sme_plans = [

        {
            "network": "MTN",
            "type": "SME",
            "name": "200MB",
            "price": 170,
            "duration": "7 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "500MB",
            "price": 285,
            "duration": "2 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "500MB",
            "price": 298,
            "duration": "14 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "1GB",
            "price": 430,
            "duration": "7 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "1GB",
            "price": 470,
            "duration": "14 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "1GB",
            "price": 550,
            "duration": "30 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "2GB",
            "price": 830,
            "duration": "14 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "2GB",
            "price": 850,
            "duration": "30 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "3GB",
            "price": 1250,
            "duration": "30 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "5GB",
            "price": 1998,
            "duration": "30 Days",
            "active": True
        },

        {
            "network": "MTN",
            "type": "SME",
            "name": "10GB",
            "price": 4498,
            "duration": "30 Days",
            "active": True
        }
    ]


    for plan in mtn_sme_plans:

        plans.update_one(
            {
                "network": plan["network"],
                "type": plan["type"],
                "name": plan["name"],
                "duration": plan["duration"]
            },

            {
                "$set": {
                    "price": plan["price"],
                    "active": plan["active"]
                }
            },

            upsert=True
        )


# =========================================================
# ADMIN SEED
# =========================================================

def seed_admin():

    existing_admin = users.find_one(
        {
            "email": "admin@example.com"
        }
    )


    if not existing_admin:

        users.insert_one(
            {
                "name": "Admin",
                "email": "admin@example.com",
                "password": generate_password_hash("Admin123!"),
                "role": "admin",
                "wallet": 0,
                "created_at": datetime.utcnow()
            }
        )


# =========================================================
# LOGIN HELPERS
# =========================================================

def current_user():

    user_id = session.get("user_id")


    if not user_id:

        return None


    try:

        return users.find_one(
            {
                "_id": ObjectId(user_id)
            }
        )

    except Exception:

        return None


@app.context_processor
def inject_user():

    return {
        "logged_user": current_user()
    }


def login_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if not session.get("user_id"):

            flash(
                "Please log in to continue.",
                "error"
            )

            return redirect(
                url_for("login")
            )

        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        user = current_user()


        if not user or user.get("role") != "admin":

            flash(
                "Administrator access required.",
                "error"
            )

            return redirect(
                url_for("dashboard")
            )

        return view(*args, **kwargs)

    return wrapped_view


# =========================================================
# HOME
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# =========================================================
# REGISTRATION WITH EMAIL VERIFICATION
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    # Validate required fields
    if not all([name, email, phone, password, confirm_password]):
        flash("Please complete all registration fields.", "error")
        return redirect(url_for("register"))

    # Validate name
    if len(name) < 2:
        flash("Please enter your full name.", "error")
        return redirect(url_for("register"))

    # Validate Nigerian phone number
    if not re.fullmatch(r"0[789][01]\d{8}", phone):
        flash("Enter a valid Nigerian phone number.", "error")
        return redirect(url_for("register"))

    # Validate email
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("register"))

    # Validate password
    if len(password) < 6:
        flash("Your password must contain at least 6 characters.", "error")
        return redirect(url_for("register"))

    if password != confirm_password:
        flash("Your passwords do not match.", "error")
        return redirect(url_for("register"))

    # Check whether the email already belongs to an account
    if users.find_one({"email": email}):
        flash("An account with this email already exists.", "error")
        return redirect(url_for("register"))

    # Check whether the phone number already belongs to an account
    if users.find_one({"phone": phone}):
        flash("This phone number is already registered.", "error")
        return redirect(url_for("register"))

    now = datetime.utcnow()

    # Apply a cooldown to repeated verification requests
    existing_pending = pending_registrations.find_one({"email": email})

    if existing_pending:
        last_sent = existing_pending.get("last_sent_at", now)

        elapsed = (now - last_sent).total_seconds()

        if elapsed < 60:
            remaining = max(1, int(60 - elapsed))
            flash(
                f"Please wait {remaining} seconds before requesting another code.",
                "error"
            )
            return redirect(url_for("register"))

    # Generate a six-digit verification code
    verification_code = f"{secrets.randbelow(1000000):06d}"

    code_hash = hashlib.sha256(
        verification_code.encode("utf-8")
    ).hexdigest()

    pending_data = {
        "name": name,
        "email": email,
        "phone": phone,
        "password": generate_password_hash(password),
        "code_hash": code_hash,
        "created_at": now,
        "expires_at": now + timedelta(minutes=10),
        "last_sent_at": now,
        "attempts": 0
    }

    # Save pending registration, not a completed user account
    pending_registrations.update_one(
        {"email": email},
        {"$set": pending_data},
        upsert=True
    )

    # Send the code using Brevo
    if not send_verification_email(email, verification_code):

        pending_registrations.delete_one({"email": email})

        app.logger.error(
            "Verification email could not be sent to the recipient."
        )

        flash(
            "We could not send your verification email. Please try again later.",
            "error"
        )

        return redirect(url_for("register"))

    # Remember which email is awaiting verification
    session["pending_registration_email"] = email

    flash(
        "A verification code has been sent to your email. "
        "It expires in 10 minutes.",
        "success"
    )

    return redirect(url_for("verify_email"))


# =========================================================
# VERIFY EMAIL ADDRESS
# =========================================================

@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():

    email = session.get("pending_registration_email")

    if not email:
        flash("Please register first to request a verification code.", "error")
        return redirect(url_for("register"))

    pending = pending_registrations.find_one({"email": email})

    if not pending:
        session.pop("pending_registration_email", None)

        flash(
            "Your pending registration was not found. Please register again.",
            "error"
        )

        return redirect(url_for("register"))

    if request.method == "GET":
        return render_template("verify_email.html", email=email)

    code = request.form.get("verification_code", "").strip()

    if not re.fullmatch(r"\d{6}", code):
        flash("Enter the six-digit verification code.", "error")
        return redirect(url_for("verify_email"))

    now = datetime.utcnow()

    # Reject expired codes
    if now > pending["expires_at"]:
        flash(
            "Your verification code has expired. Request a new one.",
            "error"
        )
        return redirect(url_for("verify_email"))

    # Limit verification attempts
    if pending.get("attempts", 0) >= 5:
        flash(
            "Too many incorrect attempts. Request a new verification code.",
            "error"
        )
        return redirect(url_for("verify_email"))

    submitted_hash = hashlib.sha256(
        code.encode("utf-8")
    ).hexdigest()

    if not hmac.compare_digest(
        submitted_hash,
        pending["code_hash"]
    ):

        pending_registrations.update_one(
            {"email": email},
            {"$inc": {"attempts": 1}}
        )

        flash("Incorrect verification code. Please try again.", "error")
        return redirect(url_for("verify_email"))

    # Check again to prevent duplicate accounts
    if users.find_one({
        "$or": [
            {"email": pending["email"]},
            {"phone": pending["phone"]}
        ]
    }):

        pending_registrations.delete_one({"email": email})
        session.pop("pending_registration_email", None)

        flash(
            "An account with this email or phone number already exists. "
            "Please sign in.",
            "error"
        )

        return redirect(url_for("login"))

    # Create the account only after successful verification
    result = users.insert_one({
        "name": pending["name"],
        "email": pending["email"],
        "phone": pending["phone"],
        "password": pending["password"],
        "role": "staff",
        "wallet": 0,
        "email_verified": True,
        "created_at": now
    })

    # Remove pending registration
    pending_registrations.delete_one({"email": email})
    session.pop("pending_registration_email", None)

    # Log in the verified user
    session["user_id"] = str(result.inserted_id)

    flash("Email verified! Your DataHub account is ready.", "success")

    return redirect(url_for("dashboard"))


# =========================================================
# RESEND VERIFICATION CODE
# =========================================================

@app.route("/resend-verification", methods=["POST"])
def resend_verification():

    email = session.get("pending_registration_email")

    if not email:
        flash("Please register first.", "error")
        return redirect(url_for("register"))

    pending = pending_registrations.find_one({"email": email})

    if not pending:
        session.pop("pending_registration_email", None)
        flash("Registration not found. Please register again.", "error")
        return redirect(url_for("register"))

    now = datetime.utcnow()
    last_sent = pending.get("last_sent_at", now)

    if (now - last_sent).total_seconds() < 60:
        flash(
            "Please wait at least 60 seconds before requesting another code.",
            "error"
        )
        return redirect(url_for("verify_email"))

    verification_code = f"{secrets.randbelow(1000000):06d}"

    code_hash = hashlib.sha256(
        verification_code.encode("utf-8")
    ).hexdigest()

    # Update the code before sending it
    pending_registrations.update_one(
        {"email": email},
        {
            "$set": {
                "code_hash": code_hash,
                "expires_at": now + timedelta(minutes=10),
                "last_sent_at": now,
                "attempts": 0
            }
        }
    )

    if not send_verification_email(email, verification_code):
        flash(
            "We could not send a new code. Please try again later.",
            "error"
        )
        return redirect(url_for("verify_email"))

    flash("A new verification code has been sent to your email.", "success")

    return redirect(url_for("verify_email"))

def send_password_reset_email(recipient_email, reset_url):
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")

    if not api_key or not sender_email:
        app.logger.error("Brevo password-reset configuration is missing.")
        return False

    payload = {
        "sender": {
            "name": "DataHub",
            "email": sender_email
        },
        "to": [{"email": recipient_email}],
        "subject": "Reset Your DataHub Password",
        "htmlContent": f"""
        <div style="font-family:Arial,sans-serif;
                    max-width:500px;margin:auto;padding:25px;">
            <h2>Reset your DataHub password</h2>
            <p>We received a request to reset your password.</p>
            <p>
                <a href="{reset_url}"
                   style="display:inline-block;padding:12px 20px;
                          background:#ffd400;color:#222;
                          text-decoration:none;border-radius:8px;
                          font-weight:bold;">
                    Reset Password
                </a>
            </p>
            <p>This link expires in 30 minutes and can only be used once.</p>
            <p>If you did not request this, you can ignore this email.</p>
        </div>
        """
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": api_key,
                "content-type": "application/json"
            },
            json=payload,
            timeout=20
        )

        if response.status_code in (200, 201, 202):
            return True

        app.logger.error(
            "Brevo password-reset email failed: HTTP %s",
            response.status_code
        )
        return False

    except requests.RequestException:
        app.logger.exception("Password-reset email could not be sent.")
        return False
# =========================================================
# WEBAUTHN FINGERPRINT REGISTRATION
# =========================================================

@app.route(
    "/webauthn/register/options",
    methods=["POST"]
)
@login_required
def webauthn_register_options():

    user_id = session.get(
        "user_id"
    )


    try:

        user = users.find_one(
            {
                "_id": ObjectId(user_id)
            }
        )

    except Exception:

        user = None


    if not user:

        return {
            "error": "User not found."
        }, 404


    # -----------------------------------------------------
    # CREATE WEBAUTHN USER ID
    # -----------------------------------------------------

    webauthn_user_id = str(
        user["_id"]
    ).encode("utf-8")


    # -----------------------------------------------------
    # GENERATE REGISTRATION OPTIONS
    # -----------------------------------------------------

    options = generate_registration_options(

        rp_id=WEBAUTHN_RP_ID,

        rp_name=WEBAUTHN_RP_NAME,

        user_name=user.get(
            "email",
            ""
        ),

        user_id=webauthn_user_id,

        user_display_name=user.get(
            "name",
            "DataHub User"
        ),
    )


    # -----------------------------------------------------
    # SAVE CHALLENGE IN SESSION
    # -----------------------------------------------------

    session[
        "webauthn_registration_challenge"
    ] = base64.b64encode(
        options.challenge
    ).decode("utf-8")


    # -----------------------------------------------------
    # CONVERT OPTIONS TO JSON
    # -----------------------------------------------------

    return {
        "options": options_to_json(
            options
        )
    }


# =========================================================
# WEBAUTHN FINGERPRINT REGISTRATION VERIFICATION
# =========================================================

@app.route(
    "/webauthn/register/verify",
    methods=["POST"]
)
@login_required
def webauthn_register_verify():

    user_id = session.get(
        "user_id"
    )


    challenge_b64 = session.get(
        "webauthn_registration_challenge"
    )


    if not challenge_b64:

        return {
            "error": "Registration session expired. Please try again."
        }, 400


    expected_challenge = base64.b64decode(
        challenge_b64
    )


    credential = request.get_json()


    if not credential:

        return {
            "error": "No WebAuthn credential was received."
        }, 400


    # -----------------------------------------------------
    # VERIFY REGISTRATION
    # -----------------------------------------------------

    try:

        verification = verify_registration_response(

            credential=credential,

            expected_challenge=expected_challenge,

            expected_rp_id=WEBAUTHN_RP_ID,

            expected_origin=WEBAUTHN_ORIGIN,
        )


    except Exception as e:

        return {
            "error": (
                "Fingerprint registration failed: "
                + str(e)
            )
        }, 400


    # -----------------------------------------------------
    # SAVE CREDENTIAL
    # -----------------------------------------------------

    webauthn_credentials.insert_one(
        {
            "user_id": ObjectId(user_id),

            "credential_id": verification.credential_id,

            "public_key": verification.credential_public_key,

            "sign_count": verification.sign_count,

            "created_at": datetime.utcnow()
        }
    )


    # -----------------------------------------------------
    # REMOVE USED CHALLENGE
    # -----------------------------------------------------

    session.pop(
        "webauthn_registration_challenge",
        None
    )


    return {
        "success": True,

        "message": (
            "Fingerprint login has been registered successfully."
        )
    }
# =========================================================
# WEBAUTHN FINGERPRINT LOGIN OPTIONS
# =========================================================

@app.route(
    "/webauthn/login/options",
    methods=["POST"]
)
def webauthn_login_options():

    options = generate_authentication_options(
        rp_id=WEBAUTHN_RP_ID
    )

    session[
        "webauthn_authentication_challenge"
    ] = base64.b64encode(
        options.challenge
    ).decode("utf-8")

    return {
        "options": options_to_json(
            options
        )
    }


# =========================================================
# WEBAUTHN FINGERPRINT LOGIN VERIFICATION
# =========================================================

@app.route(
    "/webauthn/login/verify",
    methods=["POST"]
)
def webauthn_login_verify():

    challenge_b64 = session.get(
        "webauthn_authentication_challenge"
    )

    if not challenge_b64:

        return {
            "error": "Authentication session expired. Please try again."
        }, 400


    expected_challenge = base64.b64decode(
        challenge_b64
    )


    credential = request.get_json()


    if not credential:

        return {
            "error": "No WebAuthn credential was received."
        }, 400


    # -----------------------------------------------------
    # GET CREDENTIAL ID FROM BROWSER RESPONSE
    # -----------------------------------------------------

    credential_id_string = credential.get(
        "rawId"
    ) or credential.get(
        "id"
    )


    if not credential_id_string:

        return {
            "error": "Credential ID was not received."
        }, 400


    try:

        credential_id = base64url_to_bytes(
            credential_id_string
        )

    except Exception:

        return {
            "error": "Invalid WebAuthn credential ID."
        }, 400


    # -----------------------------------------------------
    # FIND STORED CREDENTIAL
    # -----------------------------------------------------

    stored_credential = webauthn_credentials.find_one(
        {
            "credential_id": credential_id
        }
    )


    if not stored_credential:

        return {
            "error": (
                "This device has not been registered "
                "for fingerprint login."
            )
        }, 404


    # -----------------------------------------------------
    # VERIFY AUTHENTICATION
    # -----------------------------------------------------

    try:

        verification = verify_authentication_response(

            credential=credential,

            expected_challenge=expected_challenge,

            expected_rp_id=WEBAUTHN_RP_ID,

            expected_origin=WEBAUTHN_ORIGIN,

            credential_public_key=stored_credential[
                "public_key"
            ],

            credential_current_sign_count=stored_credential.get(
                "sign_count",
                0
            ),

            require_user_verification=True,
        )


    except Exception as e:

        return {
            "error": (
                "Fingerprint authentication failed: "
                + str(e)
            )
        }, 400


    # -----------------------------------------------------
    # UPDATE SIGN COUNT
    # -----------------------------------------------------

    webauthn_credentials.update_one(

        {
            "_id": stored_credential["_id"]
        },

        {
            "$set": {
                "sign_count": verification.new_sign_count
            }
        }
    )


    # -----------------------------------------------------
    # LOG USER IN
    # -----------------------------------------------------

    user = users.find_one(
        {
            "_id": stored_credential["user_id"]
        }
    )


    if not user:

        return {
            "error": "User account could not be found."
        }, 404


    session["user_id"] = str(
        user["_id"]
    )


    # -----------------------------------------------------
    # REMOVE USED CHALLENGE
    # -----------------------------------------------------

    session.pop(
        "webauthn_authentication_challenge",
        None
    )


    return {
        "success": True,

        "message": (
            f"Welcome back, "
            f"{user.get('name', 'User')}!"
        ),

        "redirect": url_for(
            "dashboard"
        )
    }

# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )


        user = users.find_one(
            {
                "email": email
            }
        )


        if not user or not check_password_hash(
            user.get(
                "password",
                ""
            ),
            password
        ):

            flash(
                "Invalid email or password.",
                "error"
            )

            return redirect(
                url_for("login")
            )


        session["user_id"] = str(
            user["_id"]
        )


        flash(
            f"Welcome back, {user.get('name', 'User')}!",
            "success"
        )


        return redirect(
            url_for("dashboard")
        )


    return render_template(
        "login.html"
    )
# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    email = request.form.get("email", "").strip().lower()
    now = datetime.utcnow()

    # Always use a general response to avoid revealing
    # whether an email address has an account.
    message = (
        "If an account exists for that email, "
        "a password-reset link will be sent shortly."
    )

    if not email or not re.fullmatch(
        r"[^@\s]+@[^@\s]+\.[^@\s]+", email
    ):
        flash(message, "success")
        return redirect(url_for("forgot_password"))

    user = users.find_one({"email": email})

    if not user:
        flash(message, "success")
        return redirect(url_for("forgot_password"))

    # Limit repeated reset emails for the same account.
    previous = password_resets.find_one({"email": email})

    if previous:
        last_sent = previous.get("last_sent_at")

        if last_sent and (now - last_sent).total_seconds() < 60:
            flash(message, "success")
            return redirect(url_for("forgot_password"))

    # Generate a random token; store only its hash.
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    reset_url = (
    "https://datahub-vtu.onrender.com"
    + url_for("reset_password", token=token)
)
    # Send first, then save the usable token only if sending succeeds.
    if not send_password_reset_email(email, reset_url):
        flash(
            "We could not send the reset email right now. Please try again later.",
            "error"
        )
        return redirect(url_for("forgot_password"))

    password_resets.update_one(
        {"email": email},
        {
            "$set": {
                "email": email,
                "token_hash": token_hash,
                "expires_at": now + timedelta(minutes=30),
                "last_sent_at": now
            }
        },
        upsert=True
    )

    flash(message, "success")
    return redirect(url_for("forgot_password"))


# =========================================================
# RESET PASSWORD
# =========================================================

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = datetime.utcnow()

    reset_request = password_resets.find_one({
        "token_hash": token_hash,
        "expires_at": {"$gt": now}
    })

    if not reset_request:
        flash(
            "This password-reset link is invalid or has expired. "
            "Please request another one.",
            "error"
        )
        return redirect(url_for("forgot_password"))

    if request.method == "GET":
        return render_template("reset_password.html")

    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if len(password) < 8:
        flash("Your new password must contain at least 8 characters.", "error")
        return redirect(url_for("reset_password", token=token))

    if password != confirm_password:
        flash("The passwords do not match.", "error")
        return redirect(url_for("reset_password", token=token))

    result = users.update_one(
        {"email": reset_request["email"]},
        {"$set": {"password": generate_password_hash(password)}}
    )

    if result.matched_count != 1:
        flash("The account could not be found. Please try again.", "error")
        return redirect(url_for("forgot_password"))

    # Delete the token so it cannot be reused.
    password_resets.delete_one({"_id": reset_request["_id"]})

    flash("Your password has been reset. You can now sign in.", "success")
    return redirect(url_for("login"))

# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()


    flash(
        "You have been logged out.",
        "success"
    )


    return redirect(
        url_for("login")
    )


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
@login_required
def dashboard():

    user = current_user()


    recent_transactions = list(
        transactions.find(
            {
                "user_id": user["_id"]
            }
        )
        .sort(
            "created_at",
            -1
        )
        .limit(5)
    )


    return render_template(

        "dashboard.html",

        user=user,

        recent_transactions=recent_transactions
    )


# =========================================================
# BUY DATA
# =========================================================

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy_data():

    user = current_user()


    if request.method == "POST":

        plan_id = request.form.get(
            "plan_id"
        )

        phone = request.form.get(
            "phone",
            ""
        ).strip()


        if not plan_id:

            flash(
                "Please select a data plan.",
                "error"
            )

            return redirect(
                url_for("buy_data")
            )


        if len(phone) != 11 or not phone.isdigit():

            flash(
                "Please enter a valid 11-digit Nigerian phone number.",
                "error"
            )

            return redirect(
                url_for("buy_data")
            )


        try:

            plan = plans.find_one(
                {
                    "_id": ObjectId(plan_id),
                    "active": True
                }
            )

        except Exception:

            plan = None


        if not plan:

            flash(
                "The selected data plan is unavailable.",
                "error"
            )

            return redirect(
                url_for("buy_data")
            )


        amount = int(
            plan["price"]
        )


        result = users.update_one(

            {
                "_id": user["_id"],

                "wallet": {
                    "$gte": amount
                }
            },

            {
                "$inc": {
                    "wallet": -amount
                }
            }
        )


        if result.modified_count == 0:

            flash(
                "Insufficient wallet balance.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        reference = (
            "DATA-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Data",

                "network": plan.get(
                    "network"
                ),

                "plan": plan.get(
                    "name"
                ),

                "duration": plan.get(
                    "duration"
                ),

                "phone": phone,

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"{plan.get('name')} data purchase successful. "
            f"Reference: {reference}",

            "success"
        )


        return redirect(
            url_for("transactions_page")
        )


    active_plans = list(
        plans.find(
            {
                "active": True
            }
        )
    )


    active_plans.sort(

        key=lambda p: (

            p.get(
                "network",
                ""
            ),

            p.get(
                "type",
                "Gifting"
            ),

            p.get(
                "price",
                0
            )
        )
    )


    return render_template(

        "buy.html",

        user=user,

        plans=active_plans
    )


# =========================================================
# AIRTIME
# =========================================================

@app.route("/airtime", methods=["GET", "POST"])
@login_required
def buy_airtime():

    user = current_user()


    networks = [
        "MTN",
        "Airtel",
        "Glo",
        "9mobile"
    ]


    if request.method == "POST":

        network = request.form.get(
            "network",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()


        try:

            amount = int(
                amount_raw
            )

        except ValueError:

            amount = 0


        if network not in networks:

            flash(
                "Please select a valid network.",
                "error"
            )

            return redirect(
                url_for("buy_airtime")
            )


        if len(phone) != 11 or not phone.isdigit():

            flash(
                "Please enter a valid 11-digit Nigerian phone number.",
                "error"
            )

            return redirect(
                url_for("buy_airtime")
            )


        if amount < 100:

            flash(
                "Minimum airtime purchase is ₦100.",
                "error"
            )

            return redirect(
                url_for("buy_airtime")
            )


        result = users.update_one(

            {
                "_id": user["_id"],

                "wallet": {
                    "$gte": amount
                }
            },

            {
                "$inc": {
                    "wallet": -amount
                }
            }
        )


        if result.modified_count == 0:

            flash(
                "Insufficient wallet balance.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        reference = (
            "AIR-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Airtime",

                "network": network,

                "phone": phone,

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"₦{amount:,} airtime purchase successful.",

            "success"
        )


        return redirect(
            url_for("transactions_page")
        )


    return render_template(

        "airtime.html",

        user=user,

        networks=networks
    )


# =========================================================
# WALLET
# =========================================================

@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():

    user = current_user()


    if request.method == "POST":

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()


        try:

            amount = int(
                amount_raw
            )

        except ValueError:

            amount = 0


        if amount < 100:

            flash(
                "Minimum wallet funding amount is ₦100.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        users.update_one(

            {
                "_id": user["_id"]
            },

            {
                "$inc": {
                    "wallet": amount
                }
            }
        )


        reference = (
            "WAL-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Wallet Funding",

                "network": "Wallet",

                "plan": "-",

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"₦{amount:,} has been added to your wallet.",

            "success"
        )


        return redirect(
            url_for("wallet")
        )


    user = current_user()


    return render_template(

        "wallet.html",

        user=user
    )


# =========================================================
# TRANSACTIONS
# =========================================================

@app.route("/transactions")
@login_required
def transactions_page():

    user = current_user()


    user_transactions = list(

        transactions.find(

            {
                "user_id": user["_id"]
            }

        ).sort(
            "created_at",
            -1
        )
    )


    return render_template(

        "transactions.html",

        user=user,

        transactions=user_transactions
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():

    all_plans = list(

        plans.find().sort(

            [
                ("network", 1),
                ("type", 1),
                ("price", 1)
            ]
        )
    )


    return render_template(

        "admin.html",

        plans=all_plans
    )


# =========================================================
# ADMIN ADD PLAN
# =========================================================

@app.route("/admin/plan", methods=["POST"])
@admin_required
def add_plan():

    network = request.form.get(
        "network",
        ""
    ).strip()

    plan_type = request.form.get(
        "type",
        "Gifting"
    ).strip()

    name = request.form.get(
        "name",
        ""
    ).strip()

    duration = request.form.get(
        "duration",
        ""
    ).strip()

    price_raw = request.form.get(
        "price",
        ""
    ).strip()


    try:

        price = int(
            price_raw
        )

    except ValueError:

        price = 0


    if (
        not network
        or not name
        or not duration
        or price <= 0
    ):

        flash(
            "Please provide valid plan details.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    if plan_type not in [
        "Gifting",
        "SME"
    ]:

        plan_type = "Gifting"


    plans.update_one(

        {
            "network": network,

            "type": plan_type,

            "name": name,

            "duration": duration
        },

        {
            "$set": {

                "price": price,

                "active": True
            }
        },

        upsert=True
    )


    flash(
        "Data plan saved successfully.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN TOGGLE PLAN
# =========================================================

@app.route(
    "/admin/plan/<plan_id>/toggle",
    methods=["POST"]
)
@admin_required
def toggle_plan(plan_id):

    try:

        plan = plans.find_one(

            {
                "_id": ObjectId(plan_id)
            }
        )

    except Exception:

        plan = None


    if not plan:

        flash(
            "Plan not found.",
            "error"
        )

        return redirect(
            url_for("admin")
        )


    plans.update_one(

        {
            "_id": plan["_id"]
        },

        {
            "$set": {

                "active": not plan.get(
                    "active",
                    True
                )
            }
        }
    )


    flash(
        "Plan status updated.",
        "success"
    )


    return redirect(
        url_for("admin")
    )


# =========================================================
# CABLE TV
# =========================================================

@app.route("/cable", methods=["GET", "POST"])
@login_required
def cable():

    user = current_user()


    cable_packages = {

        "DStv": {

            "Padi": 4400,

            "Yanga": 6500,

            "Confam": 11000,

            "Compact": 19000,

            "Compact Plus": 30000,

            "premium": 44500
        },


        "GOtv": {

            "Smallie": 1300,

            "supa+": 16800,

            "Jolli": 4900,

            "supa": 11400,

            "Max": 7200,

            "jinja": 3900
        },


        "Startimes": {

            "Nova": 1500,

            "Basic": 3000,

            "Classic": 5000,

            "Unique": 6000
        }
    }


    if request.method == "POST":

        provider = request.form.get(
            "provider",
            ""
        ).strip()

        package = request.form.get(
            "package",
            ""
        ).strip()

        smartcard = request.form.get(
            "smartcard",
            ""
        ).strip()


        if provider not in cable_packages:

            flash(
                "Please select a valid TV provider.",
                "error"
            )

            return redirect(
                url_for("cable")
            )


        if package not in cable_packages[provider]:

            flash(
                "Please select a valid subscription package.",
                "error"
            )

            return redirect(
                url_for("cable")
            )


        if not smartcard:

            flash(
                "Please enter your SmartCard / IUC number.",
                "error"
            )

            return redirect(
                url_for("cable")
            )


        amount = cable_packages[
            provider
        ][
            package
        ]


        result = users.update_one(

            {
                "_id": user["_id"],

                "wallet": {
                    "$gte": amount
                }
            },

            {
                "$inc": {
                    "wallet": -amount
                }
            }
        )


        if result.modified_count == 0:

            flash(
                "Insufficient wallet balance.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        reference = (
            "CAB-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Cable TV",

                "network": provider,

                "plan": package,

                "smartcard": smartcard,

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"{provider} {package} subscription successful.",

            "success"
        )


        return redirect(
            url_for("transactions_page")
        )


    return render_template(

        "cable.html",

        user=user,

        cable_packages=cable_packages
    )


# =========================================================
# ELECTRICITY
# =========================================================

@app.route(
    "/electricity",
    methods=["GET", "POST"]
)
@login_required
def electricity():

    user = current_user()


    discos = [

        "Abuja Electricity Distribution Company",

        "Eko Electricity Distribution Company",

        "Ikeja Electricity Distribution Company",

        "Enugu Electricity Distribution Company",

        "Port Harcourt Electricity Distribution Company",

        "Benin Electricity Distribution Company",

        "Ibadan Electricity Distribution Company",

        "Jos Electricity Distribution Company",

        "Kaduna Electricity Distribution Company",

        "Kano Electricity Distribution Company",

        "Yola Electricity Distribution Company"
    ]


    if request.method == "POST":

        disco = request.form.get(
            "disco",
            ""
        ).strip()

        meter_type = request.form.get(
            "meter_type",
            ""
        ).strip()

        meter_number = request.form.get(
            "meter_number",
            ""
        ).strip()

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()


        try:

            amount = int(
                amount_raw
            )

        except ValueError:

            amount = 0


        if disco not in discos:

            flash(
                "Please select a valid distribution company.",
                "error"
            )

            return redirect(
                url_for("electricity")
            )


        if meter_type not in [
            "Prepaid",
            "Postpaid"
        ]:

            flash(
                "Please select a valid meter type.",
                "error"
            )

            return redirect(
                url_for("electricity")
            )


        if not meter_number:

            flash(
                "Please enter your meter number.",
                "error"
            )

            return redirect(
                url_for("electricity")
            )


        if amount < 500:

            flash(
                "Minimum electricity payment is ₦500.",
                "error"
            )

            return redirect(
                url_for("electricity")
            )


        result = users.update_one(

            {
                "_id": user["_id"],

                "wallet": {
                    "$gte": amount
                }
            },

            {
                "$inc": {
                    "wallet": -amount
                }
            }
        )


        if result.modified_count == 0:

            flash(
                "Insufficient wallet balance.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        reference = (
            "ELE-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Electricity",

                "network": disco,

                "plan": meter_type,

                "meter_number": meter_number,

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(
            "Electricity bill payment successful.",
            "success"
        )


        return redirect(
            url_for("transactions_page")
        )


    return render_template(

        "electricity.html",

        user=user,

        discos=discos
    )


# =========================================================
# EXAM PIN
# =========================================================

@app.route(
    "/exam-pin",
    methods=["GET", "POST"]
)
@login_required
def exam_pin():

    user = current_user()


    exam_packages = {

        "WAEC": {

            "Result Checker PIN": 3500
        },

        "NECO": {

            "Result Checker PIN": 1500
        },

        "JAMB": {

            "Result Checker PIN": 1500
        }
    }


    if request.method == "POST":

        body = request.form.get(
            "body",
            ""
        ).strip()

        pin_type = request.form.get(
            "pin_type",
            ""
        ).strip()

        quantity_raw = request.form.get(
            "quantity",
            "1"
        ).strip()


        try:

            quantity = int(
                quantity_raw
            )

        except ValueError:

            quantity = 0


        if body not in exam_packages:

            flash(
                "Please select a valid examination body.",
                "error"
            )

            return redirect(
                url_for("exam_pin")
            )


        if pin_type not in exam_packages[body]:

            flash(
                "Please select a valid PIN type.",
                "error"
            )

            return redirect(
                url_for("exam_pin")
            )


        if quantity < 1:

            flash(
                "Quantity must be at least 1.",
                "error"
            )

            return redirect(
                url_for("exam_pin")
            )


        unit_price = exam_packages[
            body
        ][
            pin_type
        ]


        amount = unit_price * quantity


        result = users.update_one(

            {
                "_id": user["_id"],

                "wallet": {
                    "$gte": amount
                }
            },

            {
                "$inc": {
                    "wallet": -amount
                }
            }
        )


        if result.modified_count == 0:

            flash(
                "Insufficient wallet balance.",
                "error"
            )

            return redirect(
                url_for("wallet")
            )


        reference = (
            "PIN-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Exam PIN",

                "network": body,

                "plan": pin_type,

                "quantity": quantity,

                "amount": amount,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"{quantity} examination PIN purchase successful.",

            "success"
        )


        return redirect(
            url_for("transactions_page")
        )


    return render_template(

        "exam_pin.html",

        user=user,

        exam_packages=exam_packages
    )


# =========================================================
# AIRTIME TO CASH
# =========================================================

@app.route(
    "/airtime-to-cash",
    methods=["GET", "POST"]
)
@login_required
def airtime_to_cash():

    user = current_user()


    networks = [

        "MTN",

        "Airtel",

        "Glo",

        "9mobile"
    ]


    conversion_rate = 0.80


    if request.method == "POST":

        network = request.form.get(
            "network",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        amount_raw = request.form.get(
            "amount",
            ""
        ).strip()


        try:

            amount = int(
                amount_raw
            )

        except ValueError:

            amount = 0


        if network not in networks:

            flash(
                "Please select a valid network.",
                "error"
            )

            return redirect(
                url_for("airtime_to_cash")
            )


        if len(phone) != 11 or not phone.isdigit():

            flash(
                "Please enter a valid 11-digit phone number.",
                "error"
            )

            return redirect(
                url_for("airtime_to_cash")
            )


        if amount < 500:

            flash(
                "Minimum airtime conversion amount is ₦500.",
                "error"
            )

            return redirect(
                url_for("airtime_to_cash")
            )


        cash_amount = int(
            amount * conversion_rate
        )


        users.update_one(

            {
                "_id": user["_id"]
            },

            {
                "$inc": {
                    "wallet": cash_amount
                }
            }
        )


        reference = (
            "ATC-"
            + uuid.uuid4().hex[:10].upper()
        )


        transactions.insert_one(

            {
                "user_id": user["_id"],

                "reference": reference,

                "type": "Airtime to Cash",

                "network": network,

                "phone": phone,

                "amount": cash_amount,

                "airtime_amount": amount,

                "conversion_rate": conversion_rate,

                "status": "Successful",

                "mode": "Demo",

                "created_at": datetime.utcnow()
            }
        )


        flash(

            f"₦{cash_amount:,} has been added to your wallet.",

            "success"
        )


        return redirect(
            url_for("wallet")
        )


    return render_template(

        "airtime_to_cash.html",

        user=user,

        networks=networks
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    try:

        client.admin.command(
            "ping"
        )


        return {

            "status": "ok",

            "database": "connected"
        }


    except Exception as e:

        return {

            "status": "error",

            "database": "not connected",

            "error": str(e)

        }, 500


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    seed_plans()

    seed_admin()


    print("")

    print(
        "========================================================="
    )

    print(
        "Data Subscription App"
    )

    print(
        "========================================================="
    )

    print(
        "Database: MongoDB Atlas"
    )

    print(
        "Server: http://127.0.0.1:5002"
    )

    print(
        "WebAuthn RP ID: 127.0.0.1"
    )

    print(
        "WebAuthn Origin: http://127.0.0.1:5002"
    )

    print(
        "========================================================="
    )

    print("")


    app.run(

        host="127.0.0.1",

        port=5002,

        debug=True 
    )   