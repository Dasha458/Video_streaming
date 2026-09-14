from src.core.base_error import AppError
from src.i18n import _


class InvalidCredentialsError(AppError):
    code = "INVALID_CREDENTIALS"
    status_code = 400

    def __init__(self):
        super().__init__(_("Invalid credentials"))


class UsernameEmptyError(AppError):
    code = "USERNAME_EMPTY"
    status_code = 422

    def __init__(self):
        super().__init__(_("Username cannot be empty"))


class UsernameTakenError(AppError):
    code = "USERNAME_TAKEN"
    status_code = 409

    def __init__(self):
        super().__init__(_("Username already taken"))


class IncorrectPasswordError(AppError):
    code = "INCORRECT_PASSWORD"
    status_code = 400

    def __init__(self):
        super().__init__(_("Current password is incorrect"))


class UserNotFoundError(AppError):
    code = "USER_NOT_FOUND"
    status_code = 404

    def __init__(self):
        super().__init__(_("User not found"))


class InvalidOAuthStateError(AppError):
    code = "INVALID_OAUTH_STATE"
    status_code = 400

    def __init__(self):
        super().__init__(_("Invalid OAuth state"))


class GitHubCodeExchangeError(AppError):
    code = "GITHUB_CODE_EXCHANGE_FAILED"
    status_code = 400

    def __init__(self):
        super().__init__(_("Failed to exchange GitHub code"))


class GitHubUserInfoError(AppError):
    code = "GITHUB_USER_INFO_FAILED"
    status_code = 400

    def __init__(self):
        super().__init__(_("Failed to fetch GitHub user info"))


class GitHubEmailNotFoundError(AppError):
    code = "GITHUB_EMAIL_NOT_FOUND"
    status_code = 400

    def __init__(self):
        super().__init__(_("GitHub account has no accessible email"))
