"""Read LINE display copy using the caller's existing MySQL transaction."""
import json

from domains.line.configuration import LineConfigurationKind
from infrastructure.mysql.line_configuration_publication_repository import MySqlLineConfigurationRepository
from subsystems.line.message_copy_catalog import render_copy_payload
from subsystems.line.configuration_store import read_raw_config


def configured_message_payload(connection, key, payload, variables=None):
    snapshot = MySqlLineConfigurationRepository(connection).get(LineConfigurationKind.MESSAGE_TEMPLATES)
    definition = read_raw_config("message_templates") if snapshot.revision.value == 0 and snapshot.definition_json == "{}" else json.loads(snapshot.definition_json)
    return render_copy_payload(definition, key, payload, variables)
