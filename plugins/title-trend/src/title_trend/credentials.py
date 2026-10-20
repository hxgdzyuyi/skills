from __future__ import annotations

import sys

import keyring

from .errors import SafeError

SERVICE = "title-trend.v1"
SLOTS = ("dataforseo-login", "dataforseo-password")
LEGACY_SLOTS = ("model-api-key",)
REPAIR = "系统凭证库不可用。macOS 请解锁登录 Keychain；Windows 使用 Credential Manager；Linux 安装并解锁 Secret Service 或 KWallet、启用会话 D-Bus。禁止明文或第三方文件后端。"


def secure_backend():
    try:
        backend = keyring.get_keyring()
        identity = (type(backend).__module__, type(backend).__name__)
        allowed = {
            "darwin": {("keyring.backends.macOS", "Keyring")},
            "win32": {("keyring.backends.Windows", "WinVaultKeyring")},
            "linux": {
                ("keyring.backends.SecretService", "Keyring"),
                ("keyring.backends.kwallet", "DBusKeyring"),
                ("keyring.backends.kwallet", "DBusKeyringKWallet4"),
            },
        }.get(sys.platform, set())
        if identity not in allowed or backend.priority <= 0:
            raise SafeError("keyring_unavailable", REPAIR)
        return backend
    except SafeError:
        raise
    except Exception:
        raise SafeError("keyring_unavailable", REPAIR) from None


def get_secret(slot: str, required: bool = True) -> str | None:
    if slot not in SLOTS:
        raise SafeError("credential_slot", "未知凭证项。")
    try:
        value = secure_backend().get_password(SERVICE, slot)
    except SafeError:
        raise
    except Exception:
        raise SafeError("keyring_unavailable", REPAIR) from None
    if not value and required:
        raise SafeError(
            "credential_missing", "缺少安全保存的凭证，请在本地终端运行 title-trend configure。"
        )
    return value


def set_secret(slot: str, value: str):
    if slot not in SLOTS or not value:
        raise SafeError("credential_value", "凭证不能为空。")
    try:
        secure_backend().set_password(SERVICE, slot, value)
    except SafeError:
        raise
    except Exception:
        raise SafeError("keyring_unavailable", REPAIR) from None


def credential_status() -> dict:
    # Never echo even a portion of tokens or login; fixed masking cannot reveal secret lengths.
    backend = secure_backend()
    states = {slot: bool(get_secret(slot, False)) for slot in SLOTS}
    return {
        "backend": f"{type(backend).__module__}.{type(backend).__name__}",
        "credentials": {
            slot: {
                "configured": configured,
                "display": "••••（已配置）" if configured else "未配置",
            }
            for slot, configured in states.items()
        },
    }


def delete_credentials():
    backend = secure_backend()
    for slot in (*SLOTS, *LEGACY_SLOTS):
        try:
            if backend.get_password(SERVICE, slot) is not None:
                backend.delete_password(SERVICE, slot)
        except Exception:
            raise SafeError("keyring_unavailable", REPAIR) from None
