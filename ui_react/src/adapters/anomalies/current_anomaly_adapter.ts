/** Current-only presentation adapter; it cannot synthesize workflow state. */
import type {
  CurrentAnomalyDefinitionCode,
  CurrentAnomalySummary,
} from '../../api/anomalies/current_anomaly_query_schemas';

export interface CurrentAnomalyRowViewModel {
  issueKey: string;
  definitionCode: CurrentAnomalyDefinitionCode;
  ownerDomain: string;
  severity: 'warning' | 'blocking';
  blocking: boolean;
  episodeStartedAt: string;
  lastVerifiedAt: string;
}

export function adaptCurrentAnomalySummary(item: CurrentAnomalySummary): CurrentAnomalyRowViewModel {
  return {
    issueKey: item.issue_key,
    definitionCode: item.definition_code,
    ownerDomain: item.owner_domain,
    severity: item.severity,
    blocking: item.blocking,
    episodeStartedAt: item.episode_started_at,
    lastVerifiedAt: item.last_verified_at,
  };
}
