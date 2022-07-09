# import third party libraries
from apscheduler.schedulers.background import BackgroundScheduler

# import flask libraries (Third-party libraries)
from flask import Flask
from flask_talisman import Talisman
from flask_seasurf import SeaSurf

# import local python libraries
from python_files.functions.SQLFunctions import sql_operation
from python_files.classes.Constants import CONSTANTS

# import python standard libraries
from pathlib import Path
from os import environ
from datetime import timedelta

"""------------------------------------- START OF WEB APP CONFIGS -------------------------------------"""

# general Flask configurations
app = Flask(__name__)

# flask extension that prevents cross site request forgery
app.config["CSRF_COOKIE_SECURE"] = True
app.config["CSRF_COOKIE_HTTPONLY"] = True
app.config["CSRF_COOKIE_TIMEOUT"] = timedelta(days=1)
csrf = SeaSurf(app)

# flask extension that helps set policies for the web app
csp = {
    'script-src':[
        '\'self\'',
        'https://code.jquery.com/jquery-3.6.0.min.js',
        'https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js',
        'https://cdn.jsdelivr.net/npm/less@4',
        'https://www.google.com/recaptcha/enterprise.js',
        'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/3.7.0/chart.min.js',
        
    ]
}

permissions_policy = {
    "geolocation": "()",
    "microphone": "()"
}

# nonce="{{ csp_nonce() }}"
# xss_protection is already defaulted True
talisman = Talisman(app, content_security_policy=csp, content_security_policy_nonce_in=['script-src'], permissions_policy=permissions_policy, x_xss_protection=True)

# Debug flag (will be set to false when deployed)
app.config["DEBUG_FLAG"] = CONSTANTS.DEBUG_MODE

# Maintenance mode flag
app.config["MAINTENANCE_MODE"] = False

# Session cookie configurations
# More details: https://flask.palletsprojects.com/en/2.1.x/config/?highlight=session#SECRET_KEY
# Secret key mainly for digitally signing the session cookie
# it will retrieve the secret key from Google Secret Manager API
app.config["SECRET_KEY"] = CONSTANTS.get_secret_payload(secretID=CONSTANTS.FLASK_SECRET_KEY_NAME, decodeSecret=False)

# Make it such that the session cookie will be deleted when the browser is closed
app.config["SESSION_PERMANENT"] = False
# Browsers will not allow JavaScript access to cookies marked as “HTTP only” for security.
app.config["SESSION_COOKIE_HTTPONLY"] = True
# https://flask.palletsprojects.com/en/2.1.x/security/#security-cookie
# Lax prevents sending cookies with CSRF-prone requests 
# from external sites, such as submitting a form
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# The name of the session cookie
app.config["SESSION_COOKIE_NAME"] = "session"
# Only allow the session cookie to be sent over HTTPS
app.config["SESSION_COOKIE_SECURE"] = True

# for other scheduled tasks such as deleting expired session id from the database
scheduler = BackgroundScheduler()

# Remove jinja whitespace
app.jinja_env.trim_blocks = True
app.jinja_env.lstrip_blocks = True

# Maximum file size for uploading anything to the web app's server
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024 # 200MiB

# for image uploads file path
app.config["ALLOWED_IMAGE_EXTENSIONS"] = ("png", "jpg", "jpeg")

# for course video uploads file path
app.config["COURSE_VIDEO_FOLDER"] = Path(app.root_path).joinpath("static", "course_videos")
app.config["ALLOWED_VIDEO_EXTENSIONS"] = (".mp4, .mov, .avi, .3gpp, .flv, .mpeg4, .flv, .webm, .mpegs, .wmv")

# add the constant object to the flask app
app.config["CONSTANTS"] = CONSTANTS

# import utility functions into the flask app and get neccessary functions 
# such as update_secret_key() for rotation of the secret key
with app.app_context():
    from routes.RoutesUtils import update_secret_key

# rate limiter configuration using flask limiter
with app.app_context():
    from routes.RoutesLimiter import limiter
    limiter.init_app(app)

# Register all app routes
from routes.SuperAdmin import superAdminBP
app.register_blueprint(superAdminBP)

from routes.Admin import adminBP
app.register_blueprint(adminBP)

from routes.Errors import errorBP
app.register_blueprint(errorBP)

from routes.General import generalBP
app.register_blueprint(generalBP)

with app.app_context():
    from routes.Guest import guestBP
    app.register_blueprint(guestBP)

from routes.LoggedIn import loggedInBP
app.register_blueprint(loggedInBP)

from routes.User import userBP
app.register_blueprint(userBP)

from routes.Teacher import teacherBP
app.register_blueprint(teacherBP)

"""------------------------------------- END OF WEB APP CONFIGS -------------------------------------"""

if (__name__ == "__main__"):
    scheduler.configure(timezone="Asia/Singapore") # configure timezone to always follow Singapore's timezone

    # APScheduler docs:
    # https://apscheduler.readthedocs.io/en/latest/modules/triggers/cron.html
    # Free up database of users who have not verified their email for more than 30 days
    scheduler.add_job(
        lambda: sql_operation(table="user", mode="remove_unverified_users_more_than_30_days"),
        trigger="cron", hour=23, minute=56, second=0, id="removeUnverifiedUsers"
    )
    # Free up the database of expired JWT
    scheduler.add_job(
        lambda: sql_operation(table="limited_use_jwt", mode="delete_expired_jwt"),
        trigger="cron", hour=23, minute=57, second=0, id="deleteExpiredJWT"
    )
    # Free up the database of expired sessions
    scheduler.add_job(
        lambda: sql_operation(table="session", mode="delete_expired_sessions"), 
        trigger="cron", hour=23, minute=58, second=0, id="deleteExpiredSessions"
    )
    # Free up database of expired login attempts
    scheduler.add_job(
        lambda: sql_operation(table="login_attempts", mode="reset_attempts_past_reset_date"), 
        trigger="cron", hour=23, minute=59, second=0, id="resetLockedAccounts"
    )
    # Remove user's IP address from the database if the the user has not logged in from that IP address for more than 10 days
    scheduler.add_job(
        lambda: sql_operation(table="user_ip_addresses", mode="remove_last_accessed_more_than_10_days"),
        trigger="interval", hours=1, id="removeUnusedIPAddresses"
    )
    # Re-encrypt all the encrypted data in the database due to the monthly key rotations
    scheduler.add_job(
        lambda: sql_operation(table="user", mode="re-encrypt_data_in_database"),
        trigger="cron", day="last", hour=3, minute=0, second=0, id="reEncryptDataInDatabase"
    )
    # For key rotation of the secret key for digitally signing the session cookie
    scheduler.add_job(
        update_secret_key,
        trigger="cron", day="last", hour=23, minute=59, second=59, id="updateFlaskSecretKey"
    )
    scheduler.start()

    SSL_CONTEXT = (
        CONSTANTS.CONFIG_FOLDER_PATH.joinpath("flask-cert.pem"), 
        CONSTANTS.CONFIG_FOLDER_PATH.joinpath("flask-private-key.pem")
    )
    app.run(debug=app.config["DEBUG_FLAG"], port=environ.get("PORT", 8080), ssl_context=SSL_CONTEXT)