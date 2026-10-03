#![allow(non_camel_case_types, non_snake_case, non_upper_case_globals)]

include!(concat!(env!("OUT_DIR"), "/bindings.rs"));

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn frozen_status_table_matches_conformance_contract() {
        let statuses = [
            (gnsdk_status_GNSDK_OK, 0),
            (gnsdk_status_GNSDK_OK_WARNINGS, 1),
            (gnsdk_status_GNSDK_PARTIAL_UNSUPPORTED, 2),
            (gnsdk_status_GNSDK_CANCELLED, 10),
            (gnsdk_status_GNSDK_TIMEOUT, 11),
            (gnsdk_status_GNSDK_RESOURCE_LIMITED, 12),
            (gnsdk_status_GNSDK_BUSY, 13),
            (gnsdk_status_GNSDK_STALE, 14),
            (gnsdk_status_GNSDK_PROVIDER_FAILURE, 20),
            (gnsdk_status_GNSDK_ENGINE_FAILURE, 21),
            (gnsdk_status_GNSDK_INVALID_ARGUMENT, 30),
            (gnsdk_status_GNSDK_NOT_INITIALIZED, 31),
        ];
        for (actual, expected) in statuses {
            assert_eq!(actual, expected, "generated binding drifted from status_codes.json");
        }
    }
}
