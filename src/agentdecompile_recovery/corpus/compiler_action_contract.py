"""Compiler action admission routing; calibration receipt names stay unchanged."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompilerActionContract:
    kind: str
    module: str
    root_key: str
    prefix_key: str
    binding_key: str
    observation_key: str
    no_dispatch_source: str
    before_reservation_source: str

    def _owner(self):
        from importlib import import_module
        return import_module(self.module)

    def freeze(self, params, root):
        return self._owner().freeze_catalog_parameters(params, root)

    def validate(self, params):
        return self._owner().validate_frozen_catalog_parameters(params)

    def claims(self, params):
        return self._owner().catalog_resource_claims(params)

    def child_environment(self, params):
        # Calibration retains its historical executor environment policy.
        if self.kind == 'calibration':
            return None
        return self._owner().catalog_child_environment(params)

    def output_only(self, params):
        return self.kind == 'calibration' and params.get('select-only') is True

    def probe(self, params):
        from .wineprefix_clearance import prefix_identity, wineprefix_clearance
        if self.output_only(params):
            return {'state': 'clear', 'reason': 'select_only'}
        identity = params.get(self.prefix_key)
        try:
            if not identity or prefix_identity(params['wineprefix']) != identity:
                return {'state': 'unknown', 'reason': 'prefix_identity_changed_or_missing'}
            observation = wineprefix_clearance(params['wineprefix'])
            if prefix_identity(params['wineprefix']) != identity:
                return {'state': 'unknown', 'reason': 'prefix_identity_changed_during_probe', 'observation': observation}
            evidence = observation.get('evidence') or {}
            if any(evidence.get(key) != value for key, value in identity.items()):
                return {'state': 'unknown', 'reason': 'prefix_probe_identity_mismatch', 'observation': observation}
            return observation
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return {'state': 'unknown', 'reason': 'prefix_identity_unavailable', 'error': str(exc)}


_CONTRACTS = {
    'recover.compiler-profile-corpus': CompilerActionContract(
        'calibration', 'agentdecompile_recovery.source_parity_profile_corpus',
        '_calibration-execution-root', '_calibration-prefix-identity',
        'calibrationBinding', 'calibrationObservation', 'calibration-no-dispatch-v1',
        'catalog-calibration-before-reservation-v1'),
    'recover.candidate-wave': CompilerActionContract(
        'candidate-wave', 'agentdecompile_recovery.corpus.candidate_wave',
        '_candidate-wave-execution-root', '_candidate-wave-prefix-identity',
        'candidateWaveBinding', 'candidateWaveObservation', 'candidate-wave-no-dispatch-v1',
        'catalog-candidate-wave-before-reservation-v1'),
}


def compiler_action_contract(action_id):
    return _CONTRACTS.get(action_id)
