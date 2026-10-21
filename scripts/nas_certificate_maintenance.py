"""Certificate-only NAS maintenance. No Docker socket, business DB or provider calls.

The DSM host coordinator performs bounded reloads and live probes. This process
only sees explicitly mounted certificate volumes and its private state folder.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
from uuid import uuid4

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

FORMAT = "nas-certificate-maintenance/v1"
UTC = timezone.utc


class MaintenanceError(RuntimeError):
    """A closed, non-secret failure code suitable for DSM task email."""


def _read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def _write(path: Path, value: bytes, *, uid: int | None = None, mode=0o400):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise MaintenanceError("symlink_not_allowed")
    missing = [parent for parent in path.parents if not parent.exists()]
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + "." + uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(mode)
        if uid is not None and hasattr(os, "geteuid") and os.geteuid() == 0:
            os.chown(temporary, uid, uid)
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            # Persist directory entries as well as file contents before advancing
            # the journal. New signer/journal directories must survive power loss.
            for directory in dict.fromkeys([path.parent, *missing, *(p.parent for p in missing)]):
                descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _json(path: Path, data):
    _write(path, (json.dumps(data, sort_keys=True, indent=2) + "\n").encode())


def _unlink_state(path: Path):
    path.unlink(missing_ok=True)
    if hasattr(os, "O_DIRECTORY") and path.parent.is_dir():
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def _key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _fingerprint(cert):
    return cert.fingerprint(hashes.SHA256()).hex()


def _matches(cert, key):
    return cert.public_key().public_bytes(serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo) == key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


@dataclass(frozen=True)
class Policy:
    leaf_days: int = 90
    renew_before_days: int = 30
    ca_days: int = 1825
    rotate_before_days: int = 180
    overlap_days: int = 30

    def __post_init__(self):
        if not (0 < self.renew_before_days < self.leaf_days < self.rotate_before_days < self.ca_days
                and 0 < self.overlap_days < self.rotate_before_days):
            raise MaintenanceError("invalid_certificate_policy")


class Certificates:
    def __init__(self, root: Path, mounts: Path, *, policy=None, now=None):
        self.root, self.mounts = Path(root), Path(mounts)
        self.policy = policy or Policy()
        self.now = now or datetime.now(UTC)
        self.targets = {
            "api-ca": self.mounts / "private-ca/ca.pem",
            "management-cert": self.mounts / "management-tls/server-cert.pem",
            "management-key": self.mounts / "management-tls/server-key.pem",
            "line-cert": self.mounts / "line-tls/server-cert.pem",
            "line-key": self.mounts / "line-tls/server-key.pem",
            "db-ca": self.mounts / "db-ca/ca.pem",
            "db-server-ca": self.mounts / "server-tls/ca.pem",
            "db-cert": self.mounts / "server-tls/server-cert.pem",
            "db-key": self.mounts / "server-tls/server-key.pem",
        }
        self.groups = {"api": ("management", "line"), "db": ("db",)}
        self.names = {"management": "management-api", "line": "line-api", "db": "db"}

    def _issuers(self, group):
        return {"issuer-" + group + "-cert": self.root / "issuers" / group / "ca.pem",
                "issuer-" + group + "-key": self.root / "issuers" / group / "ca-key.pem"}

    def _all_targets(self):
        return {**self.targets, **self._issuers("api"), **self._issuers("db"),
                "state": self.root / "state.json"}

    def _load_leaf(self, service):
        cert = x509.load_pem_x509_certificate(self.targets[service + "-cert"].read_bytes())
        key = serialization.load_pem_private_key(self.targets[service + "-key"].read_bytes(), None)
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if self.names[service] not in names.get_values_for_type(x509.DNSName) or not _matches(cert, key):
            raise MaintenanceError("invalid_existing_service_identity")
        return cert

    def inspect(self):
        state = _read_json(self.root / "state.json")
        if state and state.get("format") != FORMAT:
            raise MaintenanceError("unknown_certificate_state")
        result = {"format": FORMAT, "managed": state is not None, "groups": {}}
        for group, services in self.groups.items():
            roots = x509.load_pem_x509_certificates(self.targets[group + "-ca"].read_bytes())
            if not roots:
                raise MaintenanceError("empty_trust_bundle")
            for ca in roots:
                if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                    raise MaintenanceError("invalid_ca")
            leaves = {name: self._load_leaf(name) for name in services}
            for cert in leaves.values():
                if not any(_issued_by(cert, ca) for ca in roots):
                    raise MaintenanceError("untrusted_existing_certificate")
            issuer_paths = self._issuers(group)
            if state:
                ca = x509.load_pem_x509_certificate(issuer_paths["issuer-" + group + "-cert"].read_bytes())
                key = serialization.load_pem_private_key(issuer_paths["issuer-" + group + "-key"].read_bytes(), None)
                if not _matches(ca, key) or _fingerprint(ca) != state["groups"][group]["issuer"]:
                    raise MaintenanceError("issuer_state_mismatch")
                if not any(_fingerprint(ca) == _fingerprint(root) for root in roots):
                    raise MaintenanceError("issuer_not_trusted")
            else:
                if any(path.exists() for path in issuer_paths.values()):
                    raise MaintenanceError("partial_issuer_state")
                ca = roots[0]
            overlap_until = (state or {}).get("groups", {}).get(group, {}).get("overlap_until")
            rotate = not state or ca.not_valid_after_utc <= self.now + timedelta(days=self.policy.rotate_before_days)
            renew = rotate or any(cert.not_valid_after_utc <= self.now + timedelta(days=self.policy.renew_before_days)
                                  for cert in leaves.values())
            retire = bool(overlap_until and datetime.fromisoformat(overlap_until) <= self.now)
            result["groups"][group] = {"rotate": rotate, "renew": renew, "retire": retire,
                "ca_expires": ca.not_valid_after_utc.isoformat(),
                "expires": {name: cert.not_valid_after_utc.isoformat() for name, cert in leaves.items()}}
        return result

    def _authority(self, group):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Labor Union " + group + " private CA")])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(self.now - timedelta(minutes=5))
            .not_valid_after(self.now + timedelta(days=self.policy.ca_days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), False)
            .sign(key, hashes.SHA256()))
        return cert, key

    def _leaf(self, service, ca, ca_key):
        previous = self._load_leaf(service)
        key = ec.generate_private_key(ec.SECP256R1())
        cert = (x509.CertificateBuilder().subject_name(previous.subject).issuer_name(ca.subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(self.now - timedelta(minutes=5))
            .not_valid_after(min(self.now + timedelta(days=self.policy.leaf_days), ca.not_valid_after_utc))
            .add_extension(previous.extensions.get_extension_for_class(x509.SubjectAlternativeName).value, False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False)
            .sign(ca_key, hashes.SHA256()))
        return cert, key

    def _transaction(self):
        pending = _read_json(self.root / "pending.json")
        if not pending or not re.fullmatch(r"[a-f0-9]{32}", pending.get("id", "")):
            raise MaintenanceError("invalid_pending_transaction")
        directory = self.root / "transactions" / pending["id"]
        journal = _read_json(directory / "journal.json")
        if not journal or journal.get("format") != FORMAT:
            raise MaintenanceError("invalid_transaction")
        return directory, journal

    def _save_journal(self, directory, journal, phase):
        journal["phase"] = phase
        _json(directory / "journal.json", journal)

    def prepare(self):
        if (self.root / "pending.json").exists():
            _, journal = self._transaction()
            return {"status": "pending", "phase": journal["phase"]}
        inspection = self.inspect()
        actions = {g: a for g, a in inspection["groups"].items() if a["renew"] or a["retire"]}
        if not actions:
            return {"status": "unchanged"}
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        identifier = uuid4().hex
        directory = self.root / "transactions" / identifier
        directory.mkdir(parents=True)
        directory.chmod(0o700)
        state = _read_json(self.root / "state.json", {"format": FORMAT, "groups": {}})
        journal = {"format": FORMAT, "phase": "prepared", "actions": actions,
                   "old_valid": True, "files": {}, "created": self.now.isoformat()}
        for name, path in self._all_targets().items():
            if path.exists():
                _write(directory / "before" / name, path.read_bytes())
            journal["files"][name] = path.exists()
        for group, action in actions.items():
            roots = x509.load_pem_x509_certificates(self.targets[group + "-ca"].read_bytes())
            for service in self.groups[group]:
                leaf = self._load_leaf(service)
                journal["old_valid"] &= leaf.not_valid_after_utc > self.now and any(
                    _issued_by(leaf, ca) and ca.not_valid_after_utc > self.now for ca in roots)
            if action["rotate"]:
                ca, key = self._authority(group)
                _write(directory / "candidate" / ("issuer-" + group + "-cert"), _pem(ca))
                _write(directory / "candidate" / ("issuer-" + group + "-key"), _key_pem(key))
            else:
                ca = x509.load_pem_x509_certificate(self._issuers(group)["issuer-" + group + "-cert"].read_bytes())
                key = serialization.load_pem_private_key(self._issuers(group)["issuer-" + group + "-key"].read_bytes(), None)
            old_state = state["groups"].get(group, {})
            overlap = ((self.now + timedelta(days=self.policy.overlap_days)).isoformat()
                       if action["rotate"] else old_state.get("overlap_until"))
            retained = [] if action["retire"] and not action["rotate"] else [
                root for root in roots if _fingerprint(root) != _fingerprint(ca) and root.not_valid_after_utc > self.now]
            bundle = _pem(ca) + b"".join(_pem(root) for root in retained)
            _write(directory / "candidate" / (group + "-ca"), bundle)
            if group == "db":
                _write(directory / "candidate/db-server-ca", bundle)
            if action["renew"]:
                for service in self.groups[group]:
                    cert, service_key = self._leaf(service, ca, key)
                    _write(directory / "candidate" / (service + "-cert"), _pem(cert))
                    _write(directory / "candidate" / (service + "-key"), _key_pem(service_key))
            state["groups"][group] = {"issuer": _fingerprint(ca),
                "overlap_until": overlap if retained else None}
        state["last_success"] = self.now.isoformat()
        _json(directory / "candidate/state", state)
        _json(directory / "journal.json", journal)
        self._validate(directory, journal)
        _json(self.root / "pending.json", {"id": identifier})
        return {"status": "prepared", "groups": sorted(actions)}

    def _validate(self, directory, journal):
        allowed = self._all_targets()
        for candidate in (directory / "candidate").iterdir():
            if candidate.name not in allowed or candidate.is_symlink():
                raise MaintenanceError("unexpected_candidate_file")
        state = _read_json(directory / "candidate/state")
        for group, action in journal["actions"].items():
            if group not in self.groups:
                raise MaintenanceError("unexpected_certificate_group")
            roots = x509.load_pem_x509_certificates((directory / "candidate" / (group + "-ca")).read_bytes())
            current = next((ca for ca in roots if _fingerprint(ca) == state["groups"][group]["issuer"]), None)
            if current is None or current.not_valid_after_utc <= self.now:
                raise MaintenanceError("invalid_candidate_ca")
            for service in self.groups[group]:
                cert_path = directory / "candidate" / (service + "-cert")
                cert = x509.load_pem_x509_certificate((cert_path if cert_path.exists() else self.targets[service + "-cert"]).read_bytes())
                key_path = directory / "candidate" / (service + "-key")
                key = serialization.load_pem_private_key((key_path if key_path.exists() else self.targets[service + "-key"]).read_bytes(), None)
                if (not _matches(cert, key) or not _issued_by(cert, current)
                        or not cert.not_valid_before_utc <= self.now < cert.not_valid_after_utc
                        or cert.not_valid_after_utc > current.not_valid_after_utc):
                    raise MaintenanceError("invalid_candidate_certificate")
                # A power loss may leave the live cert/key pair half replaced.
                # Pin identity to the immutable pre-change snapshot, not that
                # transient pair, so an expired installation can still resume.
                previous = x509.load_pem_x509_certificate((directory / "before" / (service + "-cert")).read_bytes())
                if cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value != previous.extensions.get_extension_for_class(x509.SubjectAlternativeName).value:
                    raise MaintenanceError("candidate_identity_changed")

    def _install(self, name, data):
        target = self._all_targets()[name]
        uid = 999 if name.startswith("db-") else 1000
        private = name.endswith("-key") or name == "state" or name.startswith("issuer-")
        _write(target, data, uid=None if name == "state" or name.startswith("issuer-") else uid,
               mode=0o400 if private else 0o444)

    def trust(self):
        directory, journal = self._transaction()
        self._validate(directory, journal)
        for group in journal["actions"]:
            for name in ([group + "-ca", "db-server-ca"] if group == "db" else ["api-ca"]):
                self._install(name, (directory / "candidate" / name).read_bytes())
        self._save_journal(directory, journal, "trusted")
        return {"status": "trusted"}

    def activate(self):
        directory, journal = self._transaction()
        if journal["phase"] not in {"trusted", "activated"}:
            raise MaintenanceError("trust_must_be_installed_first")
        self._validate(directory, journal)
        for group in journal["actions"]:
            for service in self.groups[group]:
                for suffix in ("cert", "key"):
                    name = service + "-" + suffix
                    candidate = directory / "candidate" / name
                    if candidate.exists():
                        self._install(name, candidate.read_bytes())
        self._save_journal(directory, journal, "activated")
        return {"status": "activated"}

    def commit(self, *, verified=False):
        directory, journal = self._transaction()
        if journal["phase"] != "activated" or not verified:
            raise MaintenanceError("verification_required")
        self._validate(directory, journal)
        for name in self._all_targets():
            candidate = directory / "candidate" / name
            if name.startswith("issuer-") and candidate.exists():
                self._install(name, candidate.read_bytes())
        self._install("state", (directory / "candidate/state").read_bytes())
        self._save_journal(directory, journal, "committed")
        _unlink_state(self.root / "pending.json")
        return {"status": "committed", "groups": sorted(journal["actions"])}

    def rollback(self):
        directory, journal = self._transaction()
        # Expiry can occur after preparation. Never claim an expired backup is usable.
        for group in journal["actions"]:
            roots = x509.load_pem_x509_certificates((directory / "before" / (group + "-ca")).read_bytes())
            for service in self.groups[group]:
                cert = x509.load_pem_x509_certificate((directory / "before" / (service + "-cert")).read_bytes())
                if cert.not_valid_after_utc <= self.now or not any(
                        _issued_by(cert, ca) and ca.not_valid_after_utc > self.now for ca in roots):
                    raise MaintenanceError("rollback_certificate_expired_resume_required")
        for name, existed in journal["files"].items():
            if name not in self._all_targets():
                raise MaintenanceError("unexpected_rollback_target")
            if existed:
                self._install(name, (directory / "before" / name).read_bytes())
            elif name.startswith("issuer-") or name == "state":
                _unlink_state(self._all_targets()[name])
        self._save_journal(directory, journal, "rolled_back")
        _unlink_state(self.root / "pending.json")
        return {"status": "rolled_back"}

    def publish(self):
        """Public CA copies only, for the host's two existing download files."""
        for group in self.groups:
            _write(self.root / "public" / (group + "-ca.pem"), self.targets[group + "-ca"].read_bytes(), mode=0o444)
        return {"status": "public_copies_ready"}

    def serial(self, service):
        return format(self._load_leaf(service).serial_number, "x")


def _issued_by(cert, ca):
    try:
        cert.verify_directly_issued_by(ca)
        return True
    except (ValueError, TypeError, InvalidSignature):
        return False


def probe(service, expected):
    """Execute inside the corresponding API container as its existing UID."""
    if service == "db":
        from dotenv import dotenv_values
        # Match the API's existing config precedence. Never expose settings or passwords.
        settings = "/settings/app.env" if Path("/settings/app.env").is_file() else "/line-settings/app.env"
        for name, value in dotenv_values(settings).items():
            if value is not None:
                os.environ[name] = value
        # Same bootstrap boundary as nas_security_runtime.serve: read protected
        # settings as the container's bootstrap UID, then connect as UID 1000.
        from scripts.nas_appliance import _drop_privileges
        _drop_privileges()
        from infrastructure.mysql.mysql_adapter import get_connection
        connection = get_connection()
        try:
            cert = x509.load_der_x509_certificate(connection._sock.getpeercert(binary_form=True))
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        finally:
            connection.close()
    else:
        import urllib.request
        context = ssl.create_default_context(cafile="/run/private-ca/ca.pem")
        with socket.create_connection(("127.0.0.1", 8443), timeout=5) as raw:
            with context.wrap_socket(raw, server_hostname=service) as stream:
                cert = x509.load_der_x509_certificate(stream.getpeercert(binary_form=True))
        with urllib.request.urlopen("https://" + service + ":8443/health", context=context, timeout=5) as response:
            if response.status != 200:
                raise MaintenanceError("health_probe_failed")
    if format(cert.serial_number, "x") != expected:
        raise MaintenanceError("served_certificate_not_updated")
    return {"status": "verified", "service": service}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "prepare", "trust", "activate", "commit", "rollback", "publish", "serial", "probe"])
    parser.add_argument("--root", type=Path, default=Path("/maintenance"))
    parser.add_argument("--mounts", type=Path, default=Path("/certificates"))
    parser.add_argument("--service", choices=["management", "line", "db", "management-api", "line-api"])
    parser.add_argument("--expected-serial")
    parser.add_argument("--verified", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "probe":
            result = probe(args.service, args.expected_serial)
        else:
            policy = Policy(**{name: int(os.environ.get("NAS_CERT_" + name.upper(), default))
                              for name, default in Policy().__dict__.items()})
            maintenance = Certificates(args.root, args.mounts, policy=policy)
            if args.action in {"prepare", "trust", "activate", "commit", "rollback", "publish"} and not args.apply:
                raise MaintenanceError("explicit_apply_required")
            if args.action == "serial":
                print(maintenance.serial(args.service))
                return 0
            if args.action == "status":
                result = maintenance.inspect()
            elif args.action == "commit":
                result = maintenance.commit(verified=args.verified)
            else:
                result = getattr(maintenance, args.action)()
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:
        # Never print paths, PEM data, connection exceptions or command arguments.
        code = str(error) if isinstance(error, MaintenanceError) else type(error).__name__
        result = {"status": "blocked", "error": code}
        if error.args and isinstance(error.args[0], int):
            result["error_code"] = error.args[0]
        print(json.dumps(result))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
