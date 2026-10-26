"""LIFF history projection from immutable database configuration revisions."""
import json
from domains.line.configuration import LineConfigurationKind
from domains.line.identities import LineConfigurationRevision


def list_liff_history(application, actor):
    return [{"revision": str(item.revision.value), "created_at": item.created_at.isoformat(),
             "actor": item.actor_id, "reason": item.reason}
            for item in application.history(LineConfigurationKind.LIFF, actor)]


def get_liff_snapshot(revision: str, application, actor):
    if not revision.isascii() or not revision.isdecimal() or int(revision) < 1:
        return None
    snapshot = application.get_revision(LineConfigurationKind.LIFF, LineConfigurationRevision(int(revision)), actor)
    return None if snapshot is None else json.loads(snapshot.definition_json)
