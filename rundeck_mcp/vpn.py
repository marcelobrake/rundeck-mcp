"""VPN connectivity helpers using nmcli."""

import logging
import shutil
import subprocess  # nosec B404

logger = logging.getLogger("rundeck_mcp.vpn")


class VPNConnectionError(RuntimeError):
    """Raised when the required VPN is unavailable or cannot be activated."""


def _run_nmcli(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        nmcli_path = shutil.which("nmcli")
        if not nmcli_path:
            raise FileNotFoundError("nmcli not found")
        # Comando sem shell e com binário resolvido por caminho absoluto.
        return subprocess.run(
            [nmcli_path, *args],  # nosec B603
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise VPNConnectionError(
            "O comando 'nmcli' não está disponível. "
            "Conecte a VPN manualmente antes de iniciar o MCP ou instale o NetworkManager."
        ) from exc


def _format_activation_error(vpn_name: str, exc: subprocess.CalledProcessError) -> str:
    details = " ".join(
        part.strip()
        for part in ((exc.stderr or ""), (exc.stdout or ""))
        if part and part.strip()
    )

    if "No valid secrets" in details:
        return (
            f"VPN '{vpn_name}' não está ativa e a conexão automática falhou porque o "
            "NetworkManager não encontrou segredos válidos para essa conexão. "
            "Conecte a VPN manualmente antes de iniciar o MCP, ou salve as credenciais "
            "da VPN no NetworkManager/keyring para permitir o auto-connect. "
            "Se preferir evitar essa tentativa automática, defina "
            "RUNDECK_VPN_AUTO_CONNECT=false."
        )

    if details:
        return (
            f"Falha ao ativar a VPN '{vpn_name}' via nmcli: {details}. "
            "Conecte a VPN manualmente antes de iniciar o MCP ou desative "
            "RUNDECK_VPN_AUTO_CONNECT."
        )

    return (
        f"Falha ao ativar a VPN '{vpn_name}' via nmcli (exit status {exc.returncode}). "
        "Conecte a VPN manualmente antes de iniciar o MCP ou desative "
        "RUNDECK_VPN_AUTO_CONNECT."
    )


def _is_already_active_error(exc: subprocess.CalledProcessError) -> bool:
    """Return True when nmcli reports the connection is already active."""
    details = " ".join(
        part.strip()
        for part in ((exc.stderr or ""), (exc.stdout or ""))
        if part and part.strip()
    ).lower()
    return "already active" in details or "ja esta ativa" in details or "já está ativa" in details


def is_vpn_active(vpn_name: str) -> bool:
    try:
        result = _run_nmcli("connection", "show", "--active")
    except subprocess.CalledProcessError as exc:
        raise VPNConnectionError(
            f"Falha ao verificar conexões ativas no NetworkManager: {(exc.stderr or exc.stdout or '').strip()}"
        ) from exc

    active_connections = {line.split(":", 1)[0] for line in result.stdout.splitlines() if line}
    return vpn_name in active_connections


def connect_vpn(vpn_name: str) -> None:
    logger.info("Conectando à VPN '%s'...", vpn_name)
    try:
        _run_nmcli("connection", "up", vpn_name)
    except subprocess.CalledProcessError as exc:
        if _is_already_active_error(exc):
            logger.info("VPN '%s' já estava ativa durante a tentativa de conexão.", vpn_name)
            return
        raise VPNConnectionError(_format_activation_error(vpn_name, exc)) from exc
    logger.info("VPN '%s' conectada com sucesso.", vpn_name)


def ensure_vpn_connected(vpn_name: str, auto_connect: bool) -> None:
    if not auto_connect:
        logger.info(
            "Verificação automática da VPN desativada (RUNDECK_VPN_AUTO_CONNECT=false)."
        )
        return
    if is_vpn_active(vpn_name):
        logger.info("VPN '%s' já está ativa.", vpn_name)
        return
    logger.warning("VPN '%s' não está ativa.", vpn_name)
    connect_vpn(vpn_name)
