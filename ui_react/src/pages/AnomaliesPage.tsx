/**
 * Compatibility entry for existing imports.
 *
 * The current Anomalies product is current-state only; the implementation is
 * owned by CurrentAnomaliesPage and must not reintroduce retired workflows.
 */
export {
  CurrentAnomaliesPage as AnomaliesPage,
  default,
} from './CurrentAnomaliesPage';
