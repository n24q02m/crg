# CHANGELOG

<!-- version list -->

## v3.27.3 (2026-09-26)

### Bug Fixes

- **deps**: Lock file maintenance ([#1097](https://github.com/n24q02m/crg/pull/1097),
  [`89ff192`](https://github.com/n24q02m/crg/commit/89ff1928bd90f8834456a59d184a6eb25e3c4936))

- **deps**: Update fastretrieval to >=1.11.1,<2 ([#1096](https://github.com/n24q02m/crg/pull/1096),
  [`58b1559`](https://github.com/n24q02m/crg/commit/58b1559028cb323104c83b77e95560eb5c5c3c78))


## v3.27.2 (2026-09-26)

### Bug Fixes

- **deps**: Lock file maintenance ([#1095](https://github.com/n24q02m/crg/pull/1095),
  [`56c05f2`](https://github.com/n24q02m/crg/commit/56c05f213efcdaeabd97fc96445d02017e44ade3))


## v3.27.1 (2026-09-26)

### Bug Fixes

- **ci**: Keep uv sources for git-pinned hull-core
  ([`0f8eec1`](https://github.com/n24q02m/crg/commit/0f8eec1ceddf33c93e40d299d750a2b8fd7eb3ae))

### Chores

- Re-pin hull-core for chat null-content fallback
  ([`d2d890f`](https://github.com/n24q02m/crg/commit/d2d890f9d32362c2282e651f8a00f2bbab985ef1))

- Scrub WP2 residuals (dead e2e script, open_relay string, doc sweep)
  ([`debd924`](https://github.com/n24q02m/crg/commit/debd9247ec886cbe9322e0618ea475f83aecf6ac))


## v3.27.0 (2026-09-26)

### Bug Fixes

- **migrations**: 005 skip git guard for per-subject data-dir stores
  ([`5944956`](https://github.com/n24q02m/crg/commit/5944956259acd70ce76d02dd160587dbb9fa832c))

- **server**: Drop dead _maybe_include_setup_hint hook (BYOK cut residual)
  ([`87c9ce4`](https://github.com/n24q02m/crg/commit/87c9ce454501aaa2ec39373f3731739ae7247054))

- **server,tools**: Remove deleted-member imports on search/setup/http paths
  ([`edc7b5f`](https://github.com/n24q02m/crg/commit/edc7b5f24d61bd1cf8eec1089396e269750694ab))

- **wp2**: Drop mcp-core entirely; port residual tests to hull seams
  ([`91b1ddb`](https://github.com/n24q02m/crg/commit/91b1ddb20ca4957ef32bbf40b478c01a8419a5a7))

### Features

- **wp2**: De-host onto hull-core — auth scoping, model cells, config bridge
  ([`0683c62`](https://github.com/n24q02m/crg/commit/0683c62d88fbaf11aa8666a3adcf21cd357c9a63))

### Testing

- Port suite to the post-de-host surface (hull cells, no litellm/relay)
  ([`fd7795d`](https://github.com/n24q02m/crg/commit/fd7795da0f3ac268430e5d22cbef4756a2120f0d))


## v3.26.26 (2026-09-25)

### Bug Fixes

- **deps**: Lock file maintenance ([#1092](https://github.com/n24q02m/crg/pull/1092),
  [`96def1f`](https://github.com/n24q02m/crg/commit/96def1fc616a3c608f971a2d1916b7f1ca1f8cc3))


## v3.26.25 (2026-09-25)

### Bug Fixes

- **deps**: Lock file maintenance ([#1091](https://github.com/n24q02m/crg/pull/1091),
  [`487bbe9`](https://github.com/n24q02m/crg/commit/487bbe985701e7417eac9f6f6028db90f2f9c0ab))

- **deps**: Update patch dependencies ([#1090](https://github.com/n24q02m/crg/pull/1090),
  [`9ba0104`](https://github.com/n24q02m/crg/commit/9ba010455fc9131f0bb106533a048cdb9e1436e0))


## v3.26.24 (2026-09-24)

### Bug Fixes

- **deps**: Lock file maintenance ([#1088](https://github.com/n24q02m/crg/pull/1088),
  [`9981680`](https://github.com/n24q02m/crg/commit/9981680029cc3d0f89b8d76d986b8595c6d1f7a8))

- **deps**: Update patch dependencies ([#1086](https://github.com/n24q02m/crg/pull/1086),
  [`eba5ee0`](https://github.com/n24q02m/crg/commit/eba5ee09528e8c2d05233dd8749abdcac5baf0e7))


## v3.26.23 (2026-09-21)

### Bug Fixes

- Bolt optimization speed up impact payload truncation
  ([#1077](https://github.com/n24q02m/crg/pull/1077),
  [`be88254`](https://github.com/n24q02m/crg/commit/be8825418fea99e8c2c0109f8ed753dfc5399e4f))

- Sentinel [MEDIUM] Upgrade exception logging to warning to prevent masking failures
  ([#1060](https://github.com/n24q02m/crg/pull/1060),
  [`ddf02c7`](https://github.com/n24q02m/crg/commit/ddf02c710473754a5a2ec4c07459335596a3c574))

- **deps**: Update minor dependencies ([#1057](https://github.com/n24q02m/crg/pull/1057),
  [`1667bff`](https://github.com/n24q02m/crg/commit/1667bff15bf77d8d98e009b1fb6b45f4274fde7d))

- **deps**: Update python:3.13-slim-bookworm Docker digest to 2325bb2
  ([#1064](https://github.com/n24q02m/crg/pull/1064),
  [`e93f200`](https://github.com/n24q02m/crg/commit/e93f200793583ba8c214cbe69ea90a547bebc4a2))


## v3.26.22 (2026-09-20)

### Bug Fixes

- **deps**: Lock file maintenance ([#1076](https://github.com/n24q02m/crg/pull/1076),
  [`a95a0e8`](https://github.com/n24q02m/crg/commit/a95a0e879a45d23398e805485d5dc2ec768070af))


## v3.26.21 (2026-09-20)

### Bug Fixes

- **deps**: Lock file maintenance ([#1075](https://github.com/n24q02m/crg/pull/1075),
  [`ff9acca`](https://github.com/n24q02m/crg/commit/ff9acca909c79fc56c52bb28454e864ec9715681))


## v3.26.20 (2026-09-20)

### Bug Fixes

- **deps**: Lock file maintenance ([#1074](https://github.com/n24q02m/crg/pull/1074),
  [`28b0120`](https://github.com/n24q02m/crg/commit/28b012043bd005c2b6396c94dad4b62ac5d958b3))

- **deps**: Update litellm to >=1.102.0 ([#1073](https://github.com/n24q02m/crg/pull/1073),
  [`a179762`](https://github.com/n24q02m/crg/commit/a17976290077c32565660d39ebe947d8e4a20117))


## v3.26.19 (2026-09-20)

### Bug Fixes

- **deps**: Lock file maintenance ([#1072](https://github.com/n24q02m/crg/pull/1072),
  [`6cb1efa`](https://github.com/n24q02m/crg/commit/6cb1efa1743b9ac15c7e71fb2df795926caf8eba))


## v3.26.18 (2026-09-19)

### Bug Fixes

- **deps**: Lock file maintenance ([#1069](https://github.com/n24q02m/crg/pull/1069),
  [`dd365bf`](https://github.com/n24q02m/crg/commit/dd365bfe1b32d5d6d4c612904c1c299e6ce9de57))


## v3.26.17 (2026-09-19)

### Bug Fixes

- **deps**: Lock file maintenance ([#1068](https://github.com/n24q02m/crg/pull/1068),
  [`3cd1492`](https://github.com/n24q02m/crg/commit/3cd14922ed5a0227b9e09266ec0fbe997389b191))


## v3.26.16 (2026-09-19)

### Bug Fixes

- **deps**: Lock file maintenance ([#1067](https://github.com/n24q02m/crg/pull/1067),
  [`a65fe02`](https://github.com/n24q02m/crg/commit/a65fe02d171f78ec1f5f099a95607596a1a242f7))


## v3.26.15 (2026-09-19)

### Bug Fixes

- **deps**: Lock file maintenance ([#1066](https://github.com/n24q02m/crg/pull/1066),
  [`cd861d6`](https://github.com/n24q02m/crg/commit/cd861d69a1c2b5d11a057085fe27fa5a0156058c))

- **deps**: Update fastretrieval to >=1.7.1,<2 ([#1065](https://github.com/n24q02m/crg/pull/1065),
  [`ea4d850`](https://github.com/n24q02m/crg/commit/ea4d85096e2572c70210eb30776bacba51a08137))


## v3.26.14 (2026-09-18)

### Bug Fixes

- **deps**: Lock file maintenance ([#1058](https://github.com/n24q02m/crg/pull/1058),
  [`4614025`](https://github.com/n24q02m/crg/commit/46140254ebd1daa6343f8a942dee8fcfe84df66f))

- **deps**: Update patch dependencies ([#1056](https://github.com/n24q02m/crg/pull/1056),
  [`17ea4e5`](https://github.com/n24q02m/crg/commit/17ea4e595c5a32cac215d68d1c2eddd16febcbd8))

### Continuous Integration

- Fix marketplace sync chain-skip — publish-mcp-registry always skips on crg, chaining
  sync-marketplace to it blocked every release sync
  ([`2559cdb`](https://github.com/n24q02m/crg/commit/2559cdb3d9bcd6e9a602d7b47ee32446e2a878b2))


## v3.26.13 (2026-09-17)

### Bug Fixes

- **deps**: Update dawidd6/action-send-mail action to v22
  ([#1052](https://github.com/n24q02m/crg/pull/1052),
  [`422d3ec`](https://github.com/n24q02m/crg/commit/422d3ec1a85cf44e45620e0071ae8ca589ee48d7))

- **deps**: Update minor dependencies ([#1046](https://github.com/n24q02m/crg/pull/1046),
  [`7b8714a`](https://github.com/n24q02m/crg/commit/7b8714af0c34c7c689c0bdf03d0e8e86e2588710))

### Continuous Integration

- Consolidate workflows into ci.yml + cd.yml
  ([`b82eb9b`](https://github.com/n24q02m/crg/commit/b82eb9b662e52b5259ab0ec28aa1edf6c465ed12))


## v3.26.12 (2026-09-15)

### Bug Fixes

- **deps**: Update patch dependencies ([#1054](https://github.com/n24q02m/crg/pull/1054),
  [`0d31367`](https://github.com/n24q02m/crg/commit/0d313670385fbfce7e85edf5e707ac3b72020a62))


## v3.26.11 (2026-09-15)

### Bug Fixes

- **deps**: Lock file maintenance ([#1053](https://github.com/n24q02m/crg/pull/1053),
  [`ad16b6d`](https://github.com/n24q02m/crg/commit/ad16b6d331bcd695991ece07fd270abbe02352ae))


## v3.26.10 (2026-09-14)

### Bug Fixes

- **deps**: Update ty to v0.0.79 ([#1051](https://github.com/n24q02m/crg/pull/1051),
  [`8d72853`](https://github.com/n24q02m/crg/commit/8d72853a7cd06476214e748c40ae26c7ee63971f))


## v3.26.9 (2026-09-14)

### Bug Fixes

- **deps**: Lock file maintenance ([#1050](https://github.com/n24q02m/crg/pull/1050),
  [`29299bd`](https://github.com/n24q02m/crg/commit/29299bdcd76121087bf374cb759d598e48e4c752))


## v3.26.8 (2026-09-14)

### Bug Fixes

- **deps**: Lock file maintenance ([#1049](https://github.com/n24q02m/crg/pull/1049),
  [`9e2cce3`](https://github.com/n24q02m/crg/commit/9e2cce37e545fe7696dfd2bcda0bb76921cdb5db))


## v3.26.7 (2026-09-14)

### Bug Fixes

- **deps**: Lock file maintenance ([#1048](https://github.com/n24q02m/crg/pull/1048),
  [`67350c5`](https://github.com/n24q02m/crg/commit/67350c56ef47cce10c46024bc966b73bc7326fdc))


## v3.26.6 (2026-09-14)

### Bug Fixes

- **deps**: Lock file maintenance ([#1047](https://github.com/n24q02m/crg/pull/1047),
  [`a656f7e`](https://github.com/n24q02m/crg/commit/a656f7e6312806b6aec1d2650d9ea8e146c05496))


## v3.26.5 (2026-09-14)

### Bug Fixes

- Relax sunset guard to fastretrieval floor range
  ([#1032](https://github.com/n24q02m/crg/pull/1032),
  [`d3db6b7`](https://github.com/n24q02m/crg/commit/d3db6b7ab478df9f19775fc1a3ce11030c362bb1))

- **deps**: Update minor dependencies ([#1032](https://github.com/n24q02m/crg/pull/1032),
  [`d3db6b7`](https://github.com/n24q02m/crg/commit/d3db6b7ab478df9f19775fc1a3ce11030c362bb1))


## v3.26.4 (2026-09-14)

### Bug Fixes

- Bump mcp-core to 1.24.6 ([#1044](https://github.com/n24q02m/crg/pull/1044),
  [`e0c8eda`](https://github.com/n24q02m/crg/commit/e0c8eda343746eb976f7c5d4375aafe1fedae884))

### Testing

- Update sunset stable guard to core 1.24.6 + fastretrieval 1.5.0
  ([#1044](https://github.com/n24q02m/crg/pull/1044),
  [`e0c8eda`](https://github.com/n24q02m/crg/commit/e0c8eda343746eb976f7c5d4375aafe1fedae884))


## v3.26.3 (2026-09-13)

### Bug Fixes

- **deps**: Lock file maintenance ([#1043](https://github.com/n24q02m/crg/pull/1043),
  [`7f5ff06`](https://github.com/n24q02m/crg/commit/7f5ff06f966aa571053aeea07eb6d996a94e2ab5))

- **deps**: Update fastretrieval to >=1.5.0,<2 ([#1042](https://github.com/n24q02m/crg/pull/1042),
  [`502f8f2`](https://github.com/n24q02m/crg/commit/502f8f2e36388b7c8a9e6bf798f8acc40e71aed7))


## v3.26.2 (2026-09-13)

### Bug Fixes

- **deps**: Lock file maintenance ([#1041](https://github.com/n24q02m/crg/pull/1041),
  [`b4bc8be`](https://github.com/n24q02m/crg/commit/b4bc8be2fb5be1370010f69e9e35cb4d273cd0c3))

### Documentation

- **readme**: Lead install/CLI with crg script, document uvx --from form and legacy name
  ([`6c91fea`](https://github.com/n24q02m/crg/commit/6c91fea3a25580123837d5b9ef3eae4837953093))


## v3.26.1 (2026-09-13)

### Bug Fixes

- Point server.json + plugin metadata at renamed repo crg
  ([`c7b7603`](https://github.com/n24q02m/crg/commit/c7b7603b9da078dbea44132174cfb1581fdcb6c7))

### Continuous Integration

- **cd**: Add publish_existing_tag recovery dispatch (port from wet) so a rename-blocked PyPI
  publish can be replayed without a new release
  ([`3ee17ca`](https://github.com/n24q02m/crg/commit/3ee17ca1928e18ba1eff7165f00973ed75cbcd65))


## v3.26.0 (2026-09-13)

### Documentation

- Add mode badge, MCP client install matrix, and contract-aligned agent snippet
  ([`84f3c7d`](https://github.com/n24q02m/crg/commit/84f3c7d12997f2acd13c10df1c26c0a6d8e85f3c))

### Features

- CLI-first — add 'crg' command alias, repo renamed better-code-review-graph -> crg (TOOL-2 L3, PyPI
  package unchanged)
  ([`153f984`](https://github.com/n24q02m/crg/commit/153f9845b60b99f69695d90097a229f6495f23b1))


## v3.25.10 (2026-09-13)

### Bug Fixes

- Bump mcp-core to 1.24.1 ([#1031](https://github.com/n24q02m/better-code-review-graph/pull/1031),
  [`d3346fe`](https://github.com/n24q02m/better-code-review-graph/commit/d3346fe8bc2f2dc7f696335d984b5aa65c72a314))

### Testing

- Update fastretrieval stable guard to 1.4.0 (verified genuine stable on PyPI; unblocks pre-existing
  main CI failure from lock-maintenance #1038)
  ([#1031](https://github.com/n24q02m/better-code-review-graph/pull/1031),
  [`d3346fe`](https://github.com/n24q02m/better-code-review-graph/commit/d3346fe8bc2f2dc7f696335d984b5aa65c72a314))


## v3.25.9 (2026-09-12)

### Bug Fixes

- **deps**: Lock file maintenance
  ([#1038](https://github.com/n24q02m/better-code-review-graph/pull/1038),
  [`ca2e39e`](https://github.com/n24q02m/better-code-review-graph/commit/ca2e39ea411e58ca2ac5b3f00d8e7480f8db8b89))


## v3.25.8 (2026-09-12)

### Bug Fixes

- **deps**: Lock file maintenance
  ([#1037](https://github.com/n24q02m/better-code-review-graph/pull/1037),
  [`186c962`](https://github.com/n24q02m/better-code-review-graph/commit/186c96243e2edc6db3889894f0d9df72167f5ce9))


## v3.25.7 (2026-09-12)

### Bug Fixes

- **deps**: Lock file maintenance
  ([#1036](https://github.com/n24q02m/better-code-review-graph/pull/1036),
  [`2234cb6`](https://github.com/n24q02m/better-code-review-graph/commit/2234cb66fe1a08901911928a919f02b591c2a6ca))


## v3.25.6 (2026-09-12)

### Bug Fixes

- **deps**: Update patch dependencies
  ([#1034](https://github.com/n24q02m/better-code-review-graph/pull/1034),
  [`3bf050e`](https://github.com/n24q02m/better-code-review-graph/commit/3bf050ea29cc0875f397f8b3af28f4ab4f2e1303))


## v3.25.5 (2026-09-12)

### Bug Fixes

- **deps**: Lock file maintenance
  ([#1033](https://github.com/n24q02m/better-code-review-graph/pull/1033),
  [`c419cd2`](https://github.com/n24q02m/better-code-review-graph/commit/c419cd2b2680b4d8da52ece25b41ae8f2359ff26))


## v3.25.4 (2026-09-12)

### Bug Fixes

- Bolt optimize memory overhead in crg export
  ([#1029](https://github.com/n24q02m/better-code-review-graph/pull/1029),
  [`3e4d438`](https://github.com/n24q02m/better-code-review-graph/commit/3e4d438304ccd0e7c1b25050706fa8b1a7236650))


## v3.25.3 (2026-09-12)

### Bug Fixes

- Update fastretrieval stable pin expectation
  ([#1027](https://github.com/n24q02m/better-code-review-graph/pull/1027),
  [`79bb07a`](https://github.com/n24q02m/better-code-review-graph/commit/79bb07a2c0224754e36a57f712c5465fbc0a9aeb))

- **deps**: Update minor dependencies
  ([#1027](https://github.com/n24q02m/better-code-review-graph/pull/1027),
  [`79bb07a`](https://github.com/n24q02m/better-code-review-graph/commit/79bb07a2c0224754e36a57f712c5465fbc0a9aeb))

### Chores

- **release**: Fix stale two-branch comment (single-main lane)
  ([`ab7b641`](https://github.com/n24q02m/better-code-review-graph/commit/ab7b641ab9f99825ffd633ffa0a98eae8e08d858))

- **release**: Single-main release lane (staging branch retired)
  ([`06b4d8e`](https://github.com/n24q02m/better-code-review-graph/commit/06b4d8e60b529df8bcd908fa4e56a639524d2ac2))


## v3.25.2 (2026-09-12)

### Bug Fixes

- **deps**: Update dawidd6/action-send-mail action to v21
  ([#1028](https://github.com/n24q02m/better-code-review-graph/pull/1028),
  [`c3ce62e`](https://github.com/n24q02m/better-code-review-graph/commit/c3ce62eb688112da285d92e5544e1afd69c1d3f2))

### Chores

- Pin BSR action to v1.6.1 stable (6e688489)
  ([#1024](https://github.com/n24q02m/better-code-review-graph/pull/1024),
  [`f171021`](https://github.com/n24q02m/better-code-review-graph/commit/f171021700cc781bd8aa640a5f8b3c7dba340511))

- **rulesets**: Align IaC with repo-bootstrap template
  ([`9404940`](https://github.com/n24q02m/better-code-review-graph/commit/94049404c43fc7e3984bbb948f713914a798075a))


## v3.25.1 (2026-09-11)

### Bug Fixes

- **deps**: Update patch dependencies
  ([#1026](https://github.com/n24q02m/better-code-review-graph/pull/1026),
  [`f198329`](https://github.com/n24q02m/better-code-review-graph/commit/f198329fdb06326275e6d5f2a763e1b52f9f73d7))


## v3.25.0 (2026-09-11)

### Bug Fixes

- Bolt optimization for full graph exports peak memory overhead
  ([#1015](https://github.com/n24q02m/better-code-review-graph/pull/1015),
  [`6ed06b0`](https://github.com/n24q02m/better-code-review-graph/commit/6ed06b017a869ab0d035e4ef131021bdac29f803))

- Bolt optimization push node kind filtering to sqlite in keyword fallback search
  ([#1021](https://github.com/n24q02m/better-code-review-graph/pull/1021),
  [`ecfef5a`](https://github.com/n24q02m/better-code-review-graph/commit/ecfef5a6bbb8fb90fb3cf5aa6293663411874c85))

- Complete #1017 exporter contract (DOT/Cypher escaping, language COALESCE) on iter_raw helpers
  ([#1022](https://github.com/n24q02m/better-code-review-graph/pull/1022),
  [`48ce452`](https://github.com/n24q02m/better-code-review-graph/commit/48ce452e9f77be990a8c58417344d58f8cd4fb9f))

- Complete graph isolation and resolution contracts
  ([#1017](https://github.com/n24q02m/better-code-review-graph/pull/1017),
  [`0d3a57e`](https://github.com/n24q02m/better-code-review-graph/commit/0d3a57e1ba5456200208073bbb08a04a7b963da9))

- Isolate setup and dependency contracts
  ([#1017](https://github.com/n24q02m/better-code-review-graph/pull/1017),
  [`0d3a57e`](https://github.com/n24q02m/better-code-review-graph/commit/0d3a57e1ba5456200208073bbb08a04a7b963da9))

- Resolve bare CALLS targets against unique same-repo symbols (#1006)
  ([#1023](https://github.com/n24q02m/better-code-review-graph/pull/1023),
  [`abe6cad`](https://github.com/n24q02m/better-code-review-graph/commit/abe6cad0c3489729496c0049573265a37b18258d))

- Sentinel [REJECTED] document why dynamic SQL parameterized IN clauses are secure
  ([#1020](https://github.com/n24q02m/better-code-review-graph/pull/1020),
  [`508bfd9`](https://github.com/n24q02m/better-code-review-graph/commit/508bfd98954629a23d351d5856415fa59995e1e3))

- **deps**: Lock file maintenance
  ([#1010](https://github.com/n24q02m/better-code-review-graph/pull/1010),
  [`201fa23`](https://github.com/n24q02m/better-code-review-graph/commit/201fa23be833d4701b1e003bd6828555686f5401))

- **deps**: Update minor dependencies
  ([#989](https://github.com/n24q02m/better-code-review-graph/pull/989),
  [`3bc3682`](https://github.com/n24q02m/better-code-review-graph/commit/3bc3682387c623a59685ce7ba4ff6a8cb0b35102))

- **deps**: Update n24q02m/better-semantic-release action to v1.6.0
  ([#1007](https://github.com/n24q02m/better-code-review-graph/pull/1007),
  [`4ccb2c0`](https://github.com/n24q02m/better-code-review-graph/commit/4ccb2c05f371946c675e12019401a85f4a32037a))

- **deps**: Update patch dependencies
  ([#1018](https://github.com/n24q02m/better-code-review-graph/pull/1018),
  [`df4c1bc`](https://github.com/n24q02m/better-code-review-graph/commit/df4c1bc0dd0b1efb516d4be20b1738b18dce4abb))

- **deps**: Update patch dependencies
  ([#1009](https://github.com/n24q02m/better-code-review-graph/pull/1009),
  [`bff9e9d`](https://github.com/n24q02m/better-code-review-graph/commit/bff9e9d375f0f1ebd4cc790bb780827a15c040cf))

- **deps**: Update python-semantic-release/publish-action action to v10.6.2
  ([#1013](https://github.com/n24q02m/better-code-review-graph/pull/1013),
  [`1895ba3`](https://github.com/n24q02m/better-code-review-graph/commit/1895ba3326331f0e0621555189340939c7385d56))

- **deps**: Update python:3.13-slim-bookworm Docker digest to ed86c82
  ([#1008](https://github.com/n24q02m/better-code-review-graph/pull/1008),
  [`8ae5faa`](https://github.com/n24q02m/better-code-review-graph/commit/8ae5faa6153d4c4d150ce07683a1a8404d495d5f))

### Continuous Integration

- Wire unified merge=release ladder (push staging=beta, main=stable)
  ([`b8d4541`](https://github.com/n24q02m/better-code-review-graph/commit/b8d4541f6e955a6c8293303a1acc040e6f811265))

### Features

- Complete graph isolation and resolution contracts
  ([#1017](https://github.com/n24q02m/better-code-review-graph/pull/1017),
  [`0d3a57e`](https://github.com/n24q02m/better-code-review-graph/commit/0d3a57e1ba5456200208073bbb08a04a7b963da9))


## v3.24.0 (2026-09-02)


## v3.24.0-beta.1 (2026-09-02)

### Bug Fixes

- Bump mcp-core to 1.23.2 ([#1003](https://github.com/n24q02m/better-code-review-graph/pull/1003),
  [`c5a4e2f`](https://github.com/n24q02m/better-code-review-graph/commit/c5a4e2f16c2bb30dc3b39ba5e458f7044568b281))

### Documentation

- Describe opt-in LOCAL_RERANK_MODEL reranking accurately
  ([#1005](https://github.com/n24q02m/better-code-review-graph/pull/1005),
  [`be22aea`](https://github.com/n24q02m/better-code-review-graph/commit/be22aea828371f18be8be94d2e7ea47567091748))

### Features

- Add opt-in local semantic reranking
  ([#1004](https://github.com/n24q02m/better-code-review-graph/pull/1004),
  [`b9b7fee`](https://github.com/n24q02m/better-code-review-graph/commit/b9b7fee43ab1f03c96cec0c022e476bc95d5df97))

### Testing

- Update mcp-core pin expectation
  ([#1003](https://github.com/n24q02m/better-code-review-graph/pull/1003),
  [`c5a4e2f`](https://github.com/n24q02m/better-code-review-graph/commit/c5a4e2f16c2bb30dc3b39ba5e458f7044568b281))


## v3.23.0 (2026-08-31)


## v3.23.0-beta.1 (2026-08-31)

### Bug Fixes

- Batch repository ID lookups
  ([`dd61bbe`](https://github.com/n24q02m/better-code-review-graph/commit/dd61bbe0213b56f0dd7a1de3de0b7419d5139cd9))

- Bolt optimization replacing fetchall with cursor iteration
  ([#1000](https://github.com/n24q02m/better-code-review-graph/pull/1000),
  [`c2058e5`](https://github.com/n24q02m/better-code-review-graph/commit/c2058e5e11fe82c9a4ceb96057c7b0eaeeb15fc2))

- Cover semantic query metadata
  ([#995](https://github.com/n24q02m/better-code-review-graph/pull/995),
  [`9318b49`](https://github.com/n24q02m/better-code-review-graph/commit/9318b490dd1fc5249a04942b4b4dec350be29517))

- Narrow protocol harness text payloads
  ([#996](https://github.com/n24q02m/better-code-review-graph/pull/996),
  [`ccd60c9`](https://github.com/n24q02m/better-code-review-graph/commit/ccd60c9fbddd3b31d9b00a639a3469a77dd707da))

- Refresh lock file
  ([`3da404c`](https://github.com/n24q02m/better-code-review-graph/commit/3da404ca52a8cf72befcd36db38eb2cbfa08ae28))

- Repair registry publication and stable retrieval pins
  ([`4a1f0cd`](https://github.com/n24q02m/better-code-review-graph/commit/4a1f0cd03c819450f9377c2ee39b6e04e7485a1c))

- **deps**: Lock file maintenance
  ([#998](https://github.com/n24q02m/better-code-review-graph/pull/998),
  [`48d6423`](https://github.com/n24q02m/better-code-review-graph/commit/48d64236d76bd684f5c562ae0d32768588b3ee07))

- **deps**: Update astral-sh/setup-uv action to v10
  ([`24d5735`](https://github.com/n24q02m/better-code-review-graph/commit/24d5735fd0b88dc959cea83b7c4cc8893570e4b8))

- **deps**: Update patch dependencies
  ([#997](https://github.com/n24q02m/better-code-review-graph/pull/997),
  [`219520f`](https://github.com/n24q02m/better-code-review-graph/commit/219520f1e2230a02a86f4b8437ee4d2c8b8be2ff))

- **tests**: Prune ignored directories in worktree scan and extend CLI test coverage
  ([#1001](https://github.com/n24q02m/better-code-review-graph/pull/1001),
  [`58cd197`](https://github.com/n24q02m/better-code-review-graph/commit/58cd197d4532427d61bc477930d986f68a56afc1))

### Features

- Expose embedding selection metadata
  ([#999](https://github.com/n24q02m/better-code-review-graph/pull/999),
  [`719deec`](https://github.com/n24q02m/better-code-review-graph/commit/719deec9eefd4eb385ef85912537236152394fdd))


## v3.22.0 (2026-08-29)

### Bug Fixes

- Align code review retrieval contract
  ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

- Align code review retrieval contract
  ([#973](https://github.com/n24q02m/better-code-review-graph/pull/973),
  [`c0eccee`](https://github.com/n24q02m/better-code-review-graph/commit/c0ecceeb97c606d382edbe2cf87462722e8746ec))

- Align live tool list contract
  ([#959](https://github.com/n24q02m/better-code-review-graph/pull/959),
  [`823d773`](https://github.com/n24q02m/better-code-review-graph/commit/823d7731080fa003c9588a7cb7afde78f0d2feef))

- Batch impact radius repo filtering
  ([#970](https://github.com/n24q02m/better-code-review-graph/pull/970),
  [`ccc94c7`](https://github.com/n24q02m/better-code-review-graph/commit/ccc94c7758be2316db8551e6b7e26cd590ce094d))

- Bolt optimization of get_stats aggregate calculation
  ([#985](https://github.com/n24q02m/better-code-review-graph/pull/985),
  [`4be8ec6`](https://github.com/n24q02m/better-code-review-graph/commit/4be8ec6e743f53e6f95c670cbf094ee2373cfcfe))

- Bolt optimization push edge filtering to sqlite in find_dependents
  ([#971](https://github.com/n24q02m/better-code-review-graph/pull/971),
  [`fdc030d`](https://github.com/n24q02m/better-code-review-graph/commit/fdc030d6a5bcad9842f0416d22e703f2b7e81090))

- Cover non-qwen runtime and patch dependencies
  ([#955](https://github.com/n24q02m/better-code-review-graph/pull/955),
  [`9c661bc`](https://github.com/n24q02m/better-code-review-graph/commit/9c661bc6402e640243257b4a3cee0153e2452013))

- Detach git fallback stdin ([#960](https://github.com/n24q02m/better-code-review-graph/pull/960),
  [`190554d`](https://github.com/n24q02m/better-code-review-graph/commit/190554d354e49d2a29e16f2d7900b159af4cfcb4))

- Pin workflow actions ([#968](https://github.com/n24q02m/better-code-review-graph/pull/968),
  [`3793160`](https://github.com/n24q02m/better-code-review-graph/commit/379316018170805707fec6f46bdfd959cdf4324e))

- Preserve callback lexical scope
  ([#975](https://github.com/n24q02m/better-code-review-graph/pull/975),
  [`4bd3e63`](https://github.com/n24q02m/better-code-review-graph/commit/4bd3e63db9967dfa4d61b76bcb2a92eed7326a0a))

- Prevent argument injection in _get_git_content
  ([#984](https://github.com/n24q02m/better-code-review-graph/pull/984),
  [`ae260da`](https://github.com/n24q02m/better-code-review-graph/commit/ae260da5ad3795208588f92631eb19b7ca31dfd5))

- Push batch edge kind filtering into SQL
  ([#969](https://github.com/n24q02m/better-code-review-graph/pull/969),
  [`2624b26`](https://github.com/n24q02m/better-code-review-graph/commit/2624b2662345999e4b09e2e8055fb8e7772e9c22))

- Recognise .test./.spec. filenames when excluding test helpers
  ([#911](https://github.com/n24q02m/better-code-review-graph/pull/911),
  [`84b9e18`](https://github.com/n24q02m/better-code-review-graph/commit/84b9e181a456e5ced6661a5d822a75bd810745d1))

- Refresh crg lock metadata ([#955](https://github.com/n24q02m/better-code-review-graph/pull/955),
  [`9c661bc`](https://github.com/n24q02m/better-code-review-graph/commit/9c661bc6402e640243257b4a3cee0153e2452013))

- Route bundled skills through local cli
  ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

- Route bundled skills through local cli
  ([#973](https://github.com/n24q02m/better-code-review-graph/pull/973),
  [`c0eccee`](https://github.com/n24q02m/better-code-review-graph/commit/c0ecceeb97c606d382edbe2cf87462722e8746ec))

- **deps**: Lock file maintenance
  ([#916](https://github.com/n24q02m/better-code-review-graph/pull/916),
  [`818d566`](https://github.com/n24q02m/better-code-review-graph/commit/818d566198770f61304d8a372304b683064490f1))

- **deps**: Patch vulnerable aiohttp and cryptography
  ([#955](https://github.com/n24q02m/better-code-review-graph/pull/955),
  [`9c661bc`](https://github.com/n24q02m/better-code-review-graph/commit/9c661bc6402e640243257b4a3cee0153e2452013))

- **deps**: Pin dependencies ([#913](https://github.com/n24q02m/better-code-review-graph/pull/913),
  [`5574876`](https://github.com/n24q02m/better-code-review-graph/commit/5574876f0d3c46d463bab753f553436f0539cd87))

- **deps**: Update actions/setup-python action to v7
  ([#914](https://github.com/n24q02m/better-code-review-graph/pull/914),
  [`7b6b902`](https://github.com/n24q02m/better-code-review-graph/commit/7b6b9022544a45932bc0dbfae5bb80d3c1282821))

- **deps**: Update minor dependencies
  ([#921](https://github.com/n24q02m/better-code-review-graph/pull/921),
  [`3878982`](https://github.com/n24q02m/better-code-review-graph/commit/3878982a59ef5243809f44a83033e9b5b3f1d65e))

- **deps**: Update python:3.13-slim-bookworm Docker digest to c45a22e
  ([#950](https://github.com/n24q02m/better-code-review-graph/pull/950),
  [`2d8d72a`](https://github.com/n24q02m/better-code-review-graph/commit/2d8d72ab9239e1224d8f8f322eadb72a9f5e6170))

- **graph**: Skip empty extra JSON parsing
  ([#962](https://github.com/n24q02m/better-code-review-graph/pull/962),
  [`bab769d`](https://github.com/n24q02m/better-code-review-graph/commit/bab769d88057ddd5d54f2b3f0a29bc0283ebe6b0))

- **parser**: Emit CALLS edges for callback references and toplevel init calls
  ([#975](https://github.com/n24q02m/better-code-review-graph/pull/975),
  [`4bd3e63`](https://github.com/n24q02m/better-code-review-graph/commit/4bd3e63db9967dfa4d61b76bcb2a92eed7326a0a))

- **parser**: Preserve callback lexical scope
  ([#975](https://github.com/n24q02m/better-code-review-graph/pull/975),
  [`4bd3e63`](https://github.com/n24q02m/better-code-review-graph/commit/4bd3e63db9967dfa4d61b76bcb2a92eed7326a0a))

- **release**: Sunset public OCI publishing
  ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

- **security**: Fix yaml comment parsing in heuristic rules (fixes #980)
  ([#986](https://github.com/n24q02m/better-code-review-graph/pull/986),
  [`192b712`](https://github.com/n24q02m/better-code-review-graph/commit/192b712274c65c30ae914271625ce920ad30514e))

### Chores

- Bump better-semantic-release to v1.4.0
  ([#979](https://github.com/n24q02m/better-code-review-graph/pull/979),
  [`98d0e1e`](https://github.com/n24q02m/better-code-review-graph/commit/98d0e1e8e4de8e42432e29969eeadf0e520dc76f))

- **release**: Sunset public OCI publishing
  ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

### Documentation

- Lead with local cli installation
  ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

- Lead with local cli installation
  ([#973](https://github.com/n24q02m/better-code-review-graph/pull/973),
  [`c0eccee`](https://github.com/n24q02m/better-code-review-graph/commit/c0ecceeb97c606d382edbe2cf87462722e8746ec))

### Features

- Add crg local cli harness ([#974](https://github.com/n24q02m/better-code-review-graph/pull/974),
  [`551501b`](https://github.com/n24q02m/better-code-review-graph/commit/551501b0754dde6a0f1440a7ba1d76978346f01f))

- Add CRG local CLI harness ([#973](https://github.com/n24q02m/better-code-review-graph/pull/973),
  [`c0eccee`](https://github.com/n24q02m/better-code-review-graph/commit/c0ecceeb97c606d382edbe2cf87462722e8746ec))

### Testing

- Exercise non-qwen fastretrieval runtime
  ([#955](https://github.com/n24q02m/better-code-review-graph/pull/955),
  [`9c661bc`](https://github.com/n24q02m/better-code-review-graph/commit/9c661bc6402e640243257b4a3cee0153e2452013))


## v3.22.0-beta.1 (2026-08-15)

### Bug Fixes

- Batch incremental-update hash checks to prevent N+1 queries
  ([`24153b3`](https://github.com/n24q02m/better-code-review-graph/commit/24153b3a486e86caa9e085d8007b35654a934eb5))

- Bump mcp-core to 1.20.0 ([#894](https://github.com/n24q02m/better-code-review-graph/pull/894),
  [`f3747f1`](https://github.com/n24q02m/better-code-review-graph/commit/f3747f1f53dc8e5a0fb640c39b5c1dfd9b312384))

- Bump mcp-core to 1.21.0 ([#896](https://github.com/n24q02m/better-code-review-graph/pull/896),
  [`93b1638`](https://github.com/n24q02m/better-code-review-graph/commit/93b16386917ce95a4adcbc9de0819a6c306690b1))

- Correct bot ledger dates and record rejected proposals
  ([#893](https://github.com/n24q02m/better-code-review-graph/pull/893),
  [`bc1d3ce`](https://github.com/n24q02m/better-code-review-graph/commit/bc1d3ceb50122274a1423b942bd00ce7f6964878))

- Derive TESTED_BY edges from calls made inside test functions
  ([#906](https://github.com/n24q02m/better-code-review-graph/pull/906),
  [`946cbc2`](https://github.com/n24q02m/better-code-review-graph/commit/946cbc2236b3336dbe66e0e995bc218242d8cb6b))

- Drop bot persona labels from source comments
  ([#910](https://github.com/n24q02m/better-code-review-graph/pull/910),
  [`23a7091`](https://github.com/n24q02m/better-code-review-graph/commit/23a70913f5909fa5bc582546c441c4e5863a9213))

- Drop rangeStrategy from update-type package rules
  ([#889](https://github.com/n24q02m/better-code-review-graph/pull/889),
  [`d88a334`](https://github.com/n24q02m/better-code-review-graph/commit/d88a33464fc10c134e241844ba42c5ab5525a372))

- Gate opencode issue automation by repository permission
  ([#948](https://github.com/n24q02m/better-code-review-graph/pull/948),
  [`58f12a0`](https://github.com/n24q02m/better-code-review-graph/commit/58f12a013cf5495262f1a706a009b4a7b766cb64))

- Isolate test HOME so the suite cannot write to the developer's real home
  ([#928](https://github.com/n24q02m/better-code-review-graph/pull/928),
  [`5814f92`](https://github.com/n24q02m/better-code-review-graph/commit/5814f92ba47931269571d7d76ba7984bad86132d))

- Keep a test's own helpers out of TESTED_BY and state what the edge means
  ([#909](https://github.com/n24q02m/better-code-review-graph/pull/909),
  [`fe0e439`](https://github.com/n24q02m/better-code-review-graph/commit/fe0e43929ecc11e0da93433c114907c218649718))

- Make the decision logs a declared exception to the AI-traces ignore
  ([#899](https://github.com/n24q02m/better-code-review-graph/pull/899),
  [`95e73f8`](https://github.com/n24q02m/better-code-review-graph/commit/95e73f812af7cff31558b23996870851d1997792))

- Move the fork guard to the job condition
  ([#903](https://github.com/n24q02m/better-code-review-graph/pull/903),
  [`c16dcf8`](https://github.com/n24q02m/better-code-review-graph/commit/c16dcf8e38ab7afd8f877154fc74263d721482d5))

- Move this repo to Apache-2.0, keeping the upstream MIT terms
  ([#926](https://github.com/n24q02m/better-code-review-graph/pull/926),
  [`1900029`](https://github.com/n24q02m/better-code-review-graph/commit/19000298e817f746b3f56020f207c873bbd4fc3f))

- Negotiate a supported output_dimension for Cohere embeddings
  ([#905](https://github.com/n24q02m/better-code-review-graph/pull/905),
  [`97d5166`](https://github.com/n24q02m/better-code-review-graph/commit/97d516681ed12c298af42b50707b4410053db332))

- Never run bot governance on pull requests from forks
  ([#900](https://github.com/n24q02m/better-code-review-graph/pull/900),
  [`44bc44e`](https://github.com/n24q02m/better-code-review-graph/commit/44bc44e6fc87bdd19a411ef0520eac14cd615f20))

- Pin dev-group tooling so the lockfile cannot outrun the cooldown
  ([#902](https://github.com/n24q02m/better-code-review-graph/pull/902),
  [`f879b70`](https://github.com/n24q02m/better-code-review-graph/commit/f879b70ac34c88578e010e211b9012c8d0b58df0))

- Pin GitHub Action references to commit SHAs
  ([#883](https://github.com/n24q02m/better-code-review-graph/pull/883),
  [`518c600`](https://github.com/n24q02m/better-code-review-graph/commit/518c600435aa999ea711e49d59620a2190827b72))

- Pin the tree-sitter grammar cache so the HOME redirect cannot move it
  ([#928](https://github.com/n24q02m/better-code-review-graph/pull/928),
  [`5814f92`](https://github.com/n24q02m/better-code-review-graph/commit/5814f92ba47931269571d7d76ba7984bad86132d))

- Produce implements edges during parsing
  ([#949](https://github.com/n24q02m/better-code-review-graph/pull/949),
  [`cf410af`](https://github.com/n24q02m/better-code-review-graph/commit/cf410afd8ffa93702efe7b0e9fea43b37edd760c))

- Raise instead of parsing zero nodes when a grammar cannot load
  ([#929](https://github.com/n24q02m/better-code-review-graph/pull/929),
  [`8515ddb`](https://github.com/n24q02m/better-code-review-graph/commit/8515ddbf54c10733dfb9bfb1ae88ffa501b0e401))

- Remove redundant orphan-tag shell guard (better-semantic-release @v1 has a built-in one)
  ([#881](https://github.com/n24q02m/better-code-review-graph/pull/881),
  [`14a8eb6`](https://github.com/n24q02m/better-code-review-graph/commit/14a8eb68d098a64136103390951d213d0df39c58))

- Report an unreadable credential store instead of "not configured"
  ([#930](https://github.com/n24q02m/better-code-review-graph/pull/930),
  [`e4c6308`](https://github.com/n24q02m/better-code-review-graph/commit/e4c630857e62ecf4a114a1f064d9ba6951a93fad))

- Report unknown as null instead of faking zeroes in query responses
  ([#931](https://github.com/n24q02m/better-code-review-graph/pull/931),
  [`5167bde`](https://github.com/n24q02m/better-code-review-graph/commit/5167bdec3c47471de8c5aca50d0468bf462bb798))

- Run CodeQL on dependabot and renovate pull requests
  ([#897](https://github.com/n24q02m/better-code-review-graph/pull/897),
  [`f3cddd0`](https://github.com/n24q02m/better-code-review-graph/commit/f3cddd0eb88f43e762f5d34220aeba7ba7f05aaa))

- Stop review-delta swallowing the new grammar error
  ([#929](https://github.com/n24q02m/better-code-review-graph/pull/929),
  [`8515ddb`](https://github.com/n24q02m/better-code-review-graph/commit/8515ddbf54c10733dfb9bfb1ae88ffa501b0e401))

- Support Dart parser files ([#951](https://github.com/n24q02m/better-code-review-graph/pull/951),
  [`0aebffe`](https://github.com/n24q02m/better-code-review-graph/commit/0aebffe9da05628b7b0d88b108db2d5a43555b38))

- Use exact-match edge lookup to avoid redundant name filtering
  ([`062a62e`](https://github.com/n24q02m/better-code-review-graph/commit/062a62e8b604837a9d6f6217aa26eed0d93da3de))

- Widen the Cohere embedding width only for models that support it
  ([#907](https://github.com/n24q02m/better-code-review-graph/pull/907),
  [`a964a66`](https://github.com/n24q02m/better-code-review-graph/commit/a964a66f4521e0015e4732bcfc8cfcc1a78980d9))

- **deps**: Update actions/checkout action to v7.0.1
  ([#919](https://github.com/n24q02m/better-code-review-graph/pull/919),
  [`25ad041`](https://github.com/n24q02m/better-code-review-graph/commit/25ad041f5ed8536c4363ae8b66182b9293a45a2c))

- **deps**: Update fastmcp to >=3.4.4,<4
  ([#901](https://github.com/n24q02m/better-code-review-graph/pull/901),
  [`65d5b9f`](https://github.com/n24q02m/better-code-review-graph/commit/65d5b9f2c26d4c4fe32e1c9d91de4fcb61645281))

- **deps**: Update github/codeql-action action to v4
  ([#853](https://github.com/n24q02m/better-code-review-graph/pull/853),
  [`ecf0a99`](https://github.com/n24q02m/better-code-review-graph/commit/ecf0a99a33d779f60c014ce17aa0a3d0325b5bdb))

- **deps**: Update minor dependencies
  ([#852](https://github.com/n24q02m/better-code-review-graph/pull/852),
  [`1650f50`](https://github.com/n24q02m/better-code-review-graph/commit/1650f50d7a44f32a265f9acb8bccd75184f4145f))

- **deps**: Update python:3.13-slim-bookworm Docker digest to 9d7f287
  ([#890](https://github.com/n24q02m/better-code-review-graph/pull/890),
  [`4df60ca`](https://github.com/n24q02m/better-code-review-graph/commit/4df60ca488316e108e5a67b1ad5674ce0d46c6c8))

- **deps**: Update tree-sitter-language-pack to v1
  ([#854](https://github.com/n24q02m/better-code-review-graph/pull/854),
  [`335b805`](https://github.com/n24q02m/better-code-review-graph/commit/335b805c7bfa3bf0230b38aa1e92b693f6a91da2))

- **deps**: Update watchdog to v6
  ([#857](https://github.com/n24q02m/better-code-review-graph/pull/857),
  [`2238804`](https://github.com/n24q02m/better-code-review-graph/commit/2238804e32c148e5fdc43f81207e11313f9641be))

### Features

- Add bot PR governance workflow
  ([#898](https://github.com/n24q02m/better-code-review-graph/pull/898),
  [`dc359f7`](https://github.com/n24q02m/better-code-review-graph/commit/dc359f79eadc2d4b18e807620ba3ee47bf4aacc0))

- Add fastretrieval BYO embedding support to crg
  ([#952](https://github.com/n24q02m/better-code-review-graph/pull/952),
  [`c9ef014`](https://github.com/n24q02m/better-code-review-graph/commit/c9ef014c9e5f05a9d8d2300b8e90ce36a36397f6))

- Collect names bound at Python module level
  ([#912](https://github.com/n24q02m/better-code-review-graph/pull/912),
  [`a40cd8d`](https://github.com/n24q02m/better-code-review-graph/commit/a40cd8d76f2312e245a5378f6f96dc86aaa6c571))

- Complete the plugin trinity with three skills and two lifecycle hooks
  ([#904](https://github.com/n24q02m/better-code-review-graph/pull/904),
  [`6abc2e1`](https://github.com/n24q02m/better-code-review-graph/commit/6abc2e17ce68e1c81c9fe70c5d87019173e66480))

- Derive a stable subject from the workspace username
  ([#886](https://github.com/n24q02m/better-code-review-graph/pull/886),
  [`f49355a`](https://github.com/n24q02m/better-code-review-graph/commit/f49355ab71b9b19b1c21f4e9f95ae66c48707ba9))

- Link writers of module-level state to its readers
  ([#912](https://github.com/n24q02m/better-code-review-graph/pull/912),
  [`a40cd8d`](https://github.com/n24q02m/better-code-review-graph/commit/a40cd8d76f2312e245a5378f6f96dc86aaa6c571))

- Pin the tree-sitter shape module-level assignments parse to
  ([#912](https://github.com/n24q02m/better-code-review-graph/pull/912),
  [`a40cd8d`](https://github.com/n24q02m/better-code-review-graph/commit/a40cd8d76f2312e245a5378f6f96dc86aaa6c571))

- Record module-level state sharing between Python functions
  ([#912](https://github.com/n24q02m/better-code-review-graph/pull/912),
  [`a40cd8d`](https://github.com/n24q02m/better-code-review-graph/commit/a40cd8d76f2312e245a5378f6f96dc86aaa6c571))

- Separate reads from rebinds when a function touches module state
  ([#912](https://github.com/n24q02m/better-code-review-graph/pull/912),
  [`a40cd8d`](https://github.com/n24q02m/better-code-review-graph/commit/a40cd8d76f2312e245a5378f6f96dc86aaa6c571))

- Sync cross-promo section ([#918](https://github.com/n24q02m/better-code-review-graph/pull/918),
  [`fca64df`](https://github.com/n24q02m/better-code-review-graph/commit/fca64df2cbc2e072e504f25fe538f095eb643493))

### Testing

- Cover fastretrieval local backend paths
  ([#952](https://github.com/n24q02m/better-code-review-graph/pull/952),
  [`c9ef014`](https://github.com/n24q02m/better-code-review-graph/commit/c9ef014c9e5f05a9d8d2300b8e90ce36a36397f6))


## v3.21.0 (2026-07-18)


## v3.21.0-beta.2 (2026-07-18)

### Bug Fixes

- Classify wrapped permanent embedding errors as non-retryable
  ([#879](https://github.com/n24q02m/better-code-review-graph/pull/879),
  [`5ec1812`](https://github.com/n24q02m/better-code-review-graph/commit/5ec181227dae03cbef0d0aa759e5519d2fdb29d7))


## v3.21.0-beta.1 (2026-07-18)

### Bug Fixes

- Add orphan-tag integrity guard to release CI
  ([#872](https://github.com/n24q02m/better-code-review-graph/pull/872),
  [`6cfafa5`](https://github.com/n24q02m/better-code-review-graph/commit/6cfafa5c920a6fe60eff9de1813f2792c7bb63cc))

- Adopt better-semantic-release for built-in release guards
  ([`add33f7`](https://github.com/n24q02m/better-code-review-graph/commit/add33f754e1ba6f7875ed9b11626b332b036e536))

- Bump mcp-core floor to 1.19.0 stable
  ([#870](https://github.com/n24q02m/better-code-review-graph/pull/870),
  [`d58d4d2`](https://github.com/n24q02m/better-code-review-graph/commit/d58d4d2404cde98c3272ef578984ce3271e07072))

- Bump mcp-core to 1.20.0b2 for plugin-name and CLI fixes
  ([#876](https://github.com/n24q02m/better-code-review-graph/pull/876),
  [`4f38320`](https://github.com/n24q02m/better-code-review-graph/commit/4f383207d7c6e8307eeca4233f0fb4e3a9d45b6b))

- Make git-subprocess tests hermetic under the pre-commit hook
  ([#877](https://github.com/n24q02m/better-code-review-graph/pull/877),
  [`ca8878f`](https://github.com/n24q02m/better-code-review-graph/commit/ca8878f056d80e811ee3d86339f9a3fc31e5a757))

- Pin rangeStrategy on delayed packageRules to fix renovate artifacts failure
  ([#873](https://github.com/n24q02m/better-code-review-graph/pull/873),
  [`e30e746`](https://github.com/n24q02m/better-code-review-graph/commit/e30e7460b42d45e5c505bb998115d7cb80df10b5))

### Features

- Add PR-title conventional-commit gate + no-bump release warning
  ([#875](https://github.com/n24q02m/better-code-review-graph/pull/875),
  [`b7832c6`](https://github.com/n24q02m/better-code-review-graph/commit/b7832c646d94b5a328a016bb18910861a05f1b84))

- Document CLI and smithery in README
  ([#867](https://github.com/n24q02m/better-code-review-graph/pull/867),
  [`50f3701`](https://github.com/n24q02m/better-code-review-graph/commit/50f37012ca8f2225c706be4711c02af523386f3b))

- Per-sub custom endpoint (api_base) in relay for gateway routing
  ([#877](https://github.com/n24q02m/better-code-review-graph/pull/877),
  [`ca8878f`](https://github.com/n24q02m/better-code-review-graph/commit/ca8878f056d80e811ee3d86339f9a3fc31e5a757))

- Wrap third-party code content in XPIA envelope
  ([#869](https://github.com/n24q02m/better-code-review-graph/pull/869),
  [`efd1eb2`](https://github.com/n24q02m/better-code-review-graph/commit/efd1eb210c6d64ddebfc5ef36d5d3048d5573d4c))


## v3.20.0 (2026-07-14)

### Features

- Add mcp-server, model-context-protocol, cursor, codex, claude keywords
  ([#863](https://github.com/n24q02m/better-code-review-graph/pull/863),
  [`66ced57`](https://github.com/n24q02m/better-code-review-graph/commit/66ced5782eb7cca106f3a4a70ceb444a01b89100))

- Add smithery.yaml for stdio deployment
  ([#864](https://github.com/n24q02m/better-code-review-graph/pull/864),
  [`3acb70a`](https://github.com/n24q02m/better-code-review-graph/commit/3acb70a45858e6faa9ab3fa279d322d8a60d823f))


## v3.20.0-beta.3 (2026-07-13)

### Bug Fixes

- Correct mention gate expression (balanced parens + precedence)
  ([#860](https://github.com/n24q02m/better-code-review-graph/pull/860),
  [`61772c9`](https://github.com/n24q02m/better-code-review-graph/commit/61772c9712230138942e8b13ba3a2800d3b31fb6))

- Fold summary columns into import's raw insert for true atomicity
  ([#861](https://github.com/n24q02m/better-code-review-graph/pull/861),
  [`c41ef27`](https://github.com/n24q02m/better-code-review-graph/commit/c41ef274d3a12bf4e60a3748ff42a5d98e21790f))

- Gate oc mention job on comment author write access
  ([#860](https://github.com/n24q02m/better-code-review-graph/pull/860),
  [`61772c9`](https://github.com/n24q02m/better-code-review-graph/commit/61772c9712230138942e8b13ba3a2800d3b31fb6))

- Round-trip temporal columns, derive crg repo_id from repo root
  ([#861](https://github.com/n24q02m/better-code-review-graph/pull/861),
  [`c41ef27`](https://github.com/n24q02m/better-code-review-graph/commit/c41ef274d3a12bf4e60a3748ff42a5d98e21790f))

- Run opencode bot on hosted runners
  ([#859](https://github.com/n24q02m/better-code-review-graph/pull/859),
  [`ed82c71`](https://github.com/n24q02m/better-code-review-graph/commit/ed82c71c7163959a52e3a0cec11b95aeb006b549))

### Features

- Add graph import with a round-trip export format
  ([#861](https://github.com/n24q02m/better-code-review-graph/pull/861),
  [`c41ef27`](https://github.com/n24q02m/better-code-review-graph/commit/c41ef274d3a12bf4e60a3748ff42a5d98e21790f))


## v3.20.0-beta.2 (2026-07-12)

### Features

- Return structured content from domain tools
  ([#856](https://github.com/n24q02m/better-code-review-graph/pull/856),
  [`236f55d`](https://github.com/n24q02m/better-code-review-graph/commit/236f55de8477c72e8b3beb60c8531491f9434ef5))


## v3.20.0-beta.1 (2026-07-11)

### Bug Fixes

- Add timeout to relay setup HTTP client
  ([`dace83a`](https://github.com/n24q02m/better-code-review-graph/commit/dace83a9733e52ec8175b4e8cec68011b41b72ac))

- Bump mcp-core floor to 1.19.0b4
  ([#851](https://github.com/n24q02m/better-code-review-graph/pull/851),
  [`b118df3`](https://github.com/n24q02m/better-code-review-graph/commit/b118df30e69f7901efbdb7fc46971cd8d564c722))

- Bump n24q02m-mcp-core, qwen3-embed to tracked versions
  ([#846](https://github.com/n24q02m/better-code-review-graph/pull/846),
  [`b05c190`](https://github.com/n24q02m/better-code-review-graph/commit/b05c19083057ebdcebf08c11720aa320d37450e8))

- Enforce fix(deps) semantic commit prefix in renovate config
  ([`4886c58`](https://github.com/n24q02m/better-code-review-graph/commit/4886c5857a3390dfac361a1caa3714261685d884))

- Fail the release when the computed version already exists on the registry
  ([#844](https://github.com/n24q02m/better-code-review-graph/pull/844),
  [`32e98f9`](https://github.com/n24q02m/better-code-review-graph/commit/32e98f9efac0919e241a02ce15c3ee9b65231bb7))

- Make renovate automerge effective (isolated groups, digest+lockfile automerge, 7-day cooldown)
  ([`aaa953c`](https://github.com/n24q02m/better-code-review-graph/commit/aaa953c89016feb51c094f9dbb14dcce9dbea180))

- Optimize search_nodes SQL by dropping redundant LOWER calls
  ([`fa23634`](https://github.com/n24q02m/better-code-review-graph/commit/fa2363493b5d5dd77e41acd472fb2cee1da9a010))

### Chores

- **deps**: Lock file maintenance
  ([#837](https://github.com/n24q02m/better-code-review-graph/pull/837),
  [`fef8cb6`](https://github.com/n24q02m/better-code-review-graph/commit/fef8cb6e776184bfd5210a28bdcf15e6488cff71))

- **deps**: Update actions/checkout action to v7
  ([#849](https://github.com/n24q02m/better-code-review-graph/pull/849),
  [`d254579`](https://github.com/n24q02m/better-code-review-graph/commit/d25457939def5f1f6b3096b355df2cf5f376b5fd))

- **deps**: Update minor dependencies
  ([#848](https://github.com/n24q02m/better-code-review-graph/pull/848),
  [`4c76903`](https://github.com/n24q02m/better-code-review-graph/commit/4c76903358f78e8147030d326867e1e0c79ed67c))

### Features

- Add opencode github agent (responds to /oc)
  ([`61d60be`](https://github.com/n24q02m/better-code-review-graph/commit/61d60bed0d20aa20114e4f7e6178b775514a6f2e))

- Add review-learnings store the automated reviewer must obey
  ([`12722e7`](https://github.com/n24q02m/better-code-review-graph/commit/12722e7b6d9cffe37d7fbde20e6de62df16f68dc))

- Auto-respond only to issues and PRs opened by outside people
  ([`338408a`](https://github.com/n24q02m/better-code-review-graph/commit/338408a42adbf400fc22d65481924dd517428b76))

- Mount shared cli builder with graph build/embed subcommands
  ([#851](https://github.com/n24q02m/better-code-review-graph/pull/851),
  [`b118df3`](https://github.com/n24q02m/better-code-review-graph/commit/b118df30e69f7901efbdb7fc46971cd8d564c722))

- Reviewer must obey .github/review-learnings.md
  ([`16ec00c`](https://github.com/n24q02m/better-code-review-graph/commit/16ec00ca47b9c23a9e6d90f687978c73e65c4621))


## v3.19.1 (2026-07-05)


## v3.19.1-beta.1 (2026-07-05)

### Bug Fixes

- Combine get_stats count queries into a single query
  ([`cc619d9`](https://github.com/n24q02m/better-code-review-graph/commit/cc619d9f45f4912594b58527434e21a9e6996d96))

- Tighten default-value regex to prevent SQL injection in schema parsing
  ([`bfa1a87`](https://github.com/n24q02m/better-code-review-graph/commit/bfa1a87a46556b4c937dba2be45dd6d17b346b58))

- **deps**: Lock file maintenance
  ([`800a791`](https://github.com/n24q02m/better-code-review-graph/commit/800a791e5e0ba4cc3f938ad4fc8f89d2e3f3540c))

- **deps**: Update docker/login-action digest to af1e73f
  ([`cffaa8f`](https://github.com/n24q02m/better-code-review-graph/commit/cffaa8fa4653e106ecd2d74361b0e6169f9a8f1b))

- **deps**: Update non-major dependencies
  ([#821](https://github.com/n24q02m/better-code-review-graph/pull/821),
  [`6d34a4e`](https://github.com/n24q02m/better-code-review-graph/commit/6d34a4e85082e8ab8791977d7190bc5d05bc9e04))

### Chores

- **deps**: Update docker/build-push-action digest to 53b7df9
  ([#820](https://github.com/n24q02m/better-code-review-graph/pull/820),
  [`75c1bee`](https://github.com/n24q02m/better-code-review-graph/commit/75c1bee57445cc4407ce38f49d77736ba759a46c))

- **deps**: Update docker/setup-buildx-action digest to bb05f3f
  ([#827](https://github.com/n24q02m/better-code-review-graph/pull/827),
  [`6ff69f7`](https://github.com/n24q02m/better-code-review-graph/commit/6ff69f7e01553fd58b7c476faf40ee2a43326fb0))


## v3.19.0 (2026-07-02)

### Bug Fixes

- Bump mcp-core to 1.18.1 ([#825](https://github.com/n24q02m/better-code-review-graph/pull/825),
  [`f93b5d1`](https://github.com/n24q02m/better-code-review-graph/commit/f93b5d14a57d9dea78e57fbf96a1b9d0bfb4dfb6))

### Features

- Document vertex_express provider option
  ([#823](https://github.com/n24q02m/better-code-review-graph/pull/823),
  [`4e76aa2`](https://github.com/n24q02m/better-code-review-graph/commit/4e76aa2517d13c3d9817193459929876fe196b5b))


## v3.18.2-beta.1 (2026-07-01)

### Bug Fixes

- Add Vertex AI (Express) support to relay form and credential state
  ([#818](https://github.com/n24q02m/better-code-review-graph/pull/818),
  [`be745d3`](https://github.com/n24q02m/better-code-review-graph/commit/be745d395086072d80e33d35709a77e85397cbab))

- Bump mcp-core to 1.18.1b1 for the vertex relay dropdown fix
  ([#819](https://github.com/n24q02m/better-code-review-graph/pull/819),
  [`616f293`](https://github.com/n24q02m/better-code-review-graph/commit/616f29390e79d2eb4eb13c5c6704372883bd9e32))


## v3.18.1 (2026-07-01)

### Bug Fixes

- Shorten server.json description to satisfy MCP Registry 100-char limit
  ([#816](https://github.com/n24q02m/better-code-review-graph/pull/816),
  [`c0c4b0c`](https://github.com/n24q02m/better-code-review-graph/commit/c0c4b0cbc75918ff5cdc4cdd35e16db5a3ff0d88))


## v3.18.0 (2026-07-01)


## v3.18.0-beta.13 (2026-07-01)

### Bug Fixes

- Document all 7 query-tool actions in AGENTS and CLAUDE
  ([#814](https://github.com/n24q02m/better-code-review-graph/pull/814),
  [`857c5f5`](https://github.com/n24q02m/better-code-review-graph/commit/857c5f5bd9054bfa0d8b9bf7c6560a8f9dad5e34))

- **deps**: Update non-major dependencies
  ([#811](https://github.com/n24q02m/better-code-review-graph/pull/811),
  [`67c5999`](https://github.com/n24q02m/better-code-review-graph/commit/67c599956a37250770d7447cc98267289b3fa83d))

### Chores

- **deps**: Lock file maintenance
  ([#812](https://github.com/n24q02m/better-code-review-graph/pull/812),
  [`c199641`](https://github.com/n24q02m/better-code-review-graph/commit/c19964160c6cb4c48c9232b1a00cff5a0f22c73d))


## v3.18.0-beta.12 (2026-06-30)

### Bug Fixes

- Add tests for untested function: config_value_for_current_request
  ([`adf4ee1`](https://github.com/n24q02m/better-code-review-graph/commit/adf4ee135a51669b0d09c7977977c8ed8b2a5230))

- High complexity function: _collect_import_names
  ([`1e7e260`](https://github.com/n24q02m/better-code-review-graph/commit/1e7e26011b4b650de3c0fae1d4f55a93467dc4ae))

- High complexity function: _get_bases
  ([`954a46b`](https://github.com/n24q02m/better-code-review-graph/commit/954a46b847a10eace885b68a694b1b312adf22da))

- High complexity function: _get_name
  ([`acf34e4`](https://github.com/n24q02m/better-code-review-graph/commit/acf34e450e0fac1e199184cb72951f2bd3962f9e))

- Lock file maintenance
  ([`9927183`](https://github.com/n24q02m/better-code-review-graph/commit/9927183b90df53c87f729e565f77bfa30e232385))

- Missing error path test for typescript resolver package.json loading
  ([`698a46f`](https://github.com/n24q02m/better-code-review-graph/commit/698a46f1a5da8f967c8874c278d0f3620c921e40))

- N+1 queries in _handle_children_of and related handlers
  ([`fc64e4b`](https://github.com/n24q02m/better-code-review-graph/commit/fc64e4bbedf3887f4411af33a3294d0d8041806d))

- Overly long function: _full_build_federated
  ([`7bb087e`](https://github.com/n24q02m/better-code-review-graph/commit/7bb087e3f25a303026e8fd3582ca524faef80628))

- Overly long function: renamed_in_diff
  ([`73acc5a`](https://github.com/n24q02m/better-code-review-graph/commit/73acc5a739bd75b8de11a1b74cbf2cb0e59e0ac1))

- Whitelist schema default values to harden against SQL injection
  ([`454849a`](https://github.com/n24q02m/better-code-review-graph/commit/454849a8b797c1311d4e0976b8877b74ff3089e5))


## v3.18.0-beta.11 (2026-06-29)

### Bug Fixes

- Add allowlist/blocklist guards to TemporalIndex schema DDL
  ([`56e9eeb`](https://github.com/n24q02m/better-code-review-graph/commit/56e9eebb3b0024f21a11a6cb8447bcab6eccf554))

- Batch commit inserts in federation backfill
  ([#760](https://github.com/n24q02m/better-code-review-graph/pull/760),
  [`47029b6`](https://github.com/n24q02m/better-code-review-graph/commit/47029b62592ca66d0c40770058379dc0a96faa28))

- Close missing temporal nodes in a single update
  ([#753](https://github.com/n24q02m/better-code-review-graph/pull/753),
  [`106e2ff`](https://github.com/n24q02m/better-code-review-graph/commit/106e2ff9fedad1764703b8677d78a51a8a82a25d))

- Cover set_current_sub
  ([`a131758`](https://github.com/n24q02m/better-code-review-graph/commit/a131758f03f0914cba0f70c345df92376b7c79cb))

- Log swallowed exceptions in security-critical handlers
  ([`d27ea70`](https://github.com/n24q02m/better-code-review-graph/commit/d27ea70cac8098de1662b897dece1729b3f8581d))

- Optimize _cypher_var with precompiled regex
  ([`169b375`](https://github.com/n24q02m/better-code-review-graph/commit/169b3759e3a7f590b5ca21a65ba5f956afcd8630))

- **deps**: Update non-major dependencies
  ([#747](https://github.com/n24q02m/better-code-review-graph/pull/747),
  [`3a18f74`](https://github.com/n24q02m/better-code-review-graph/commit/3a18f74bbec1ec92f4ea2c2e84453997cd87fe3d))

### Chores

- **deps**: Lock file maintenance
  ([#748](https://github.com/n24q02m/better-code-review-graph/pull/748),
  [`98aac77`](https://github.com/n24q02m/better-code-review-graph/commit/98aac779661997e2275e61f0ad7897dedc5f7f33))

- **deps**: Update actions/setup-python digest to ece7cb0
  ([#770](https://github.com/n24q02m/better-code-review-graph/pull/770),
  [`b306463`](https://github.com/n24q02m/better-code-review-graph/commit/b306463234b7e120695cbeb39135c3bf24202038))

- **deps**: Update dawidd6/action-send-mail action to v18
  ([#774](https://github.com/n24q02m/better-code-review-graph/pull/774),
  [`a7187f5`](https://github.com/n24q02m/better-code-review-graph/commit/a7187f5428b98efdd30cc83c9c798e899ef8fdf5))

- **deps**: Update python:3.13-slim-bookworm docker digest to fcbd8df
  ([#771](https://github.com/n24q02m/better-code-review-graph/pull/771),
  [`85beee2`](https://github.com/n24q02m/better-code-review-graph/commit/85beee2425c714d199e6542a458b7195bb472074))


## v3.18.0-beta.10 (2026-06-22)

### Bug Fixes

- Port SessionStart hook to cross-platform python -c (bare .sh opened Notepad on Windows)
  ([#746](https://github.com/n24q02m/better-code-review-graph/pull/746),
  [`6a241b5`](https://github.com/n24q02m/better-code-review-graph/commit/6a241b5574c3d74dd9d670263e793d93e80dc769))

- Restore v2.0 migration section in README (test_phase_3 README guard)
  ([#743](https://github.com/n24q02m/better-code-review-graph/pull/743),
  [`805e30b`](https://github.com/n24q02m/better-code-review-graph/commit/805e30bca6e1c5c7bdd4574f2df25b750184a814))

- Rewrite README for accuracy and add Install + Configuration sections
  ([#743](https://github.com/n24q02m/better-code-review-graph/pull/743),
  [`805e30b`](https://github.com/n24q02m/better-code-review-graph/commit/805e30bca6e1c5c7bdd4574f2df25b750184a814))

### Chores

- **deps**: Lock file maintenance
  ([#744](https://github.com/n24q02m/better-code-review-graph/pull/744),
  [`66fb9bc`](https://github.com/n24q02m/better-code-review-graph/commit/66fb9bc5a1f34f1609c36f44b748837725c38659))


## v3.18.0-beta.9 (2026-06-21)

### Bug Fixes

- Bump pydantic-settings to 2.14.2 (GHSA-4xgf-cpjx-pc3j)
  ([#739](https://github.com/n24q02m/better-code-review-graph/pull/739),
  [`754b3a6`](https://github.com/n24q02m/better-code-review-graph/commit/754b3a682f2746bcc687bcacb7142d7145b6da95))

- Route per-sub creds + model chains through request-scoped dispatch
  ([#741](https://github.com/n24q02m/better-code-review-graph/pull/741),
  [`23785da`](https://github.com/n24q02m/better-code-review-graph/commit/23785da8a2420d02cc20ef1b275aa092c629760b))

- Scope graph DB per JWT sub in HTTP multi-user mode
  ([#742](https://github.com/n24q02m/better-code-review-graph/pull/742),
  [`afead8b`](https://github.com/n24q02m/better-code-review-graph/commit/afead8b8aa688944def2ed4dd578f59e13c549c0))

- **deps**: Update non-major dependencies
  ([#725](https://github.com/n24q02m/better-code-review-graph/pull/725),
  [`42dc3e9`](https://github.com/n24q02m/better-code-review-graph/commit/42dc3e9b750aeb49a96b14abc300029a4cadc8eb))

### Chores

- **deps**: Update actions/checkout action to v7
  ([#732](https://github.com/n24q02m/better-code-review-graph/pull/732),
  [`87923ac`](https://github.com/n24q02m/better-code-review-graph/commit/87923ac7dd904d1212d08924aba20f3b17c59543))

### Performance Improvements

- Optimize _sanitize_name with str.translate
  ([#737](https://github.com/n24q02m/better-code-review-graph/pull/737),
  [`7daa7fd`](https://github.com/n24q02m/better-code-review-graph/commit/7daa7fd919965bd71f30afca861f54aceea80fd6))

### Testing

- Add coverage for security/heuristic.py
  ([#710](https://github.com/n24q02m/better-code-review-graph/pull/710),
  [`9cf4333`](https://github.com/n24q02m/better-code-review-graph/commit/9cf4333f699f26250beb427f574d028e4a72b6a9))


## v3.18.0-beta.8 (2026-06-19)

### Bug Fixes

- Bump mcp-core floor to 1.18.0b14 for the key-rotation primitive
  ([`fd88d4f`](https://github.com/n24q02m/better-code-review-graph/commit/fd88d4f1bcd0a6a6769840e2a0885a2220307a49))


## v3.18.0-beta.7 (2026-06-19)

### Features

- DISABLE_LOCAL_EMBED disable-local toggle for embedding
  ([#734](https://github.com/n24q02m/better-code-review-graph/pull/734),
  [`b00b834`](https://github.com/n24q02m/better-code-review-graph/commit/b00b8344ab8b9f7b96a72273d666a6eb13f77922))


## v3.18.0-beta.6 (2026-06-15)

### Bug Fixes

- Clarify embedding-model switch requires reindex (B2 guard)
  ([#709](https://github.com/n24q02m/better-code-review-graph/pull/709),
  [`e39ed42`](https://github.com/n24q02m/better-code-review-graph/commit/e39ed42e1901b4ff5b391d828855f50b5fe99134))

- Correct relay/storage docs to match OAuth-form setup and PerPluginStore
  ([`1c044d7`](https://github.com/n24q02m/better-code-review-graph/commit/1c044d7c175f8e24f94402f0e3f5166f83428da1))

- Stop flaky model download in CI
  ([`5bbcb6b`](https://github.com/n24q02m/better-code-review-graph/commit/5bbcb6b13b49972b2eda20ae5d7779671bbdc637))


## v3.18.0-beta.5 (2026-06-13)

### Bug Fixes

- Bump deps and stop Renovate raising the semgrep floor
  ([#708](https://github.com/n24q02m/better-code-review-graph/pull/708),
  [`31c9f50`](https://github.com/n24q02m/better-code-review-graph/commit/31c9f50d6cba064991071f2accf306673a36e074))

- Config status hangs on Windows under stdio
  ([#705](https://github.com/n24q02m/better-code-review-graph/pull/705),
  [`ef38e43`](https://github.com/n24q02m/better-code-review-graph/commit/ef38e43a924ddd6f3443dd160d8bd72b99e9f8c5))

- Graph build slow on Windows under stdio (git subprocess stall)
  ([#707](https://github.com/n24q02m/better-code-review-graph/pull/707),
  [`a0dca19`](https://github.com/n24q02m/better-code-review-graph/commit/a0dca198c4062ede7b4e3efdf42cba3643b7dedc))

- Local ONNX embed hangs on Windows under stdio
  ([#706](https://github.com/n24q02m/better-code-review-graph/pull/706),
  [`aafa6fe`](https://github.com/n24q02m/better-code-review-graph/commit/aafa6febc6b3ae362e8b8aa992a5a7ea6fa2ef1a))

- Remove literal v<auto> placeholder from stabilization note
  ([#698](https://github.com/n24q02m/better-code-review-graph/pull/698),
  [`8ddf9cc`](https://github.com/n24q02m/better-code-review-graph/commit/8ddf9cc98b93a6cbe72e49898e63b50c4f7d7e08))

- Sync README tagline to current capability description
  ([#700](https://github.com/n24q02m/better-code-review-graph/pull/700),
  [`b587687`](https://github.com/n24q02m/better-code-review-graph/commit/b587687ee5027785f013d7c972fb60d89deebd15))

### Chores

- **deps**: Lock file maintenance
  ([#704](https://github.com/n24q02m/better-code-review-graph/pull/704),
  [`e7af10e`](https://github.com/n24q02m/better-code-review-graph/commit/e7af10e47f2ecbc3d649ecdb3db93d25f4407251))

- **deps**: Update python:3.13-slim-bookworm docker digest to 05b9539
  ([#702](https://github.com/n24q02m/better-code-review-graph/pull/702),
  [`ad0b213`](https://github.com/n24q02m/better-code-review-graph/commit/ad0b213876450ab27859c3851355dcf123988e60))

### Features

- Sync cross-promo section ([#701](https://github.com/n24q02m/better-code-review-graph/pull/701),
  [`1994678`](https://github.com/n24q02m/better-code-review-graph/commit/1994678e1405c93f2018a2685deec80cc9610784))


## v3.18.0-beta.4 (2026-06-12)

### Bug Fixes

- Correct summarize docstring, embedding-only manifest, and 3-pillar desc
  ([#696](https://github.com/n24q02m/better-code-review-graph/pull/696),
  [`34845c9`](https://github.com/n24q02m/better-code-review-graph/commit/34845c9f05b658eedb6484ac116dc865676fd9b4))

- Filter crg vector search by active provider to prevent cross-provider mixing
  ([#697](https://github.com/n24q02m/better-code-review-graph/pull/697),
  [`9d644f4`](https://github.com/n24q02m/better-code-review-graph/commit/9d644f4c2c6b073b0fc8fceaefcbb9f8ab1355d8))

- Pin semgrep <1.162 in renovate to stop re-proposing the mcp-conflict bump (#684)
  ([#693](https://github.com/n24q02m/better-code-review-graph/pull/693),
  [`9805e57`](https://github.com/n24q02m/better-code-review-graph/commit/9805e57e5e46ce974fabebc7146c164ce931b5c9))

- Prevent argument injection in Semgrep wrapper
  ([#687](https://github.com/n24q02m/better-code-review-graph/pull/687),
  [`85e247c`](https://github.com/n24q02m/better-code-review-graph/commit/85e247c569ca94770def1d40d95ad4cd622764e6))

- Remove orphaned Qodo pr-agent config
  ([#694](https://github.com/n24q02m/better-code-review-graph/pull/694),
  [`5062546`](https://github.com/n24q02m/better-code-review-graph/commit/506254649fc26f3b4036127d226bb70b1b0664e9))

- Remove stray plan.md artifact accidentally merged via #686
  ([#692](https://github.com/n24q02m/better-code-review-graph/pull/692),
  [`5cc4cbd`](https://github.com/n24q02m/better-code-review-graph/commit/5cc4cbd9b46c82ab159df014cc8abe4fd3894c82))

- Restore PSR changelog generation and backfill version history
  ([#695](https://github.com/n24q02m/better-code-review-graph/pull/695),
  [`e83f437`](https://github.com/n24q02m/better-code-review-graph/commit/e83f437074af25593777a89be11480d9477a57f0))

### Chores

- **deps**: Lock file maintenance
  ([#685](https://github.com/n24q02m/better-code-review-graph/pull/685),
  [`e9326f0`](https://github.com/n24q02m/better-code-review-graph/commit/e9326f05a02064f779b20b6ee693eb7a038573c4))

### Performance Improvements

- Replace .fetchall() with direct cursor iteration
  ([#686](https://github.com/n24q02m/better-code-review-graph/pull/686),
  [`8a300fe`](https://github.com/n24q02m/better-code-review-graph/commit/8a300fe3fcd5ec2642374c9e626982db8bf3f76a))


## v3.18.0-beta.3 (2026-06-11)

### Bug Fixes

- Document per-task model chains + provider->key table (drop priority-router docs)
  ([#690](https://github.com/n24q02m/better-code-review-graph/pull/690),
  [`00832a6`](https://github.com/n24q02m/better-code-review-graph/commit/00832a68670029a87b23e41014796b7e246917eb))

### Features

- Drop config(action="models") catalog-listing tool action
  ([#691](https://github.com/n24q02m/better-code-review-graph/pull/691),
  [`3220b3e`](https://github.com/n24q02m/better-code-review-graph/commit/3220b3e385dd1fabe46a6ab09341e351ba900d47))


## v3.18.0-beta.2 (2026-06-11)

### Features

- Crg per-task model chains + relay model-chain widget, drop priority-router
  ([#689](https://github.com/n24q02m/better-code-review-graph/pull/689),
  [`430efa0`](https://github.com/n24q02m/better-code-review-graph/commit/430efa024d02ba2dff28451c4101b7df68564894))


## v3.18.0-beta.1 (2026-06-11)

### Bug Fixes

- Drop env api_key when SUMMARY_MODEL overrides provider
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

- Floor litellm>=1.88.0 to clear proxy-server advisories
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

### Features

- Migrate embedding + summarizer dispatch to litellm passthrough via mcp-core[llm]
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))

- Migrate embedding + summarizer dispatch to mcp_core.llm litellm passthrough
  ([#688](https://github.com/n24q02m/better-code-review-graph/pull/688),
  [`b6deb0f`](https://github.com/n24q02m/better-code-review-graph/commit/b6deb0fd71c9100658db4250ca678cff3f129bc2))


## v3.17.2-beta.2 (2026-06-10)

### Bug Fixes

- Handle non-dict payload in live integration tests
  ([#663](https://github.com/n24q02m/better-code-review-graph/pull/663),
  [`84b464e`](https://github.com/n24q02m/better-code-review-graph/commit/84b464e70915b60cafa35a2e9754fd39fa203e4b))

- Remove forced stale module-level state and refresh state in setup_status
  ([#668](https://github.com/n24q02m/better-code-review-graph/pull/668),
  [`1018800`](https://github.com/n24q02m/better-code-review-graph/commit/1018800447dcb55bcfa686a053044c4a4df92091))

- Remove unused check_available method from embedding backends
  ([#682](https://github.com/n24q02m/better-code-review-graph/pull/682),
  [`d6e68f5`](https://github.com/n24q02m/better-code-review-graph/commit/d6e68f5c53ce29b641124b32d588010a79796372))

- Replace flaky wall-clock N+1 perf assertion with query count
  ([#683](https://github.com/n24q02m/better-code-review-graph/pull/683),
  [`6b6b8d6`](https://github.com/n24q02m/better-code-review-graph/commit/6b6b8d6a6f7386b081f068cf199ed1ab083212ec))

- Resolve historical bug in path resolution and mock embeddings in tests
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical bug in path resolution for bundled resources
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical path resolution bug and improve embedding tests reliability
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

- Resolve historical path resolution bug and mock embeddings in tests
  ([#670](https://github.com/n24q02m/better-code-review-graph/pull/670),
  [`2b30533`](https://github.com/n24q02m/better-code-review-graph/commit/2b30533e091d9afc54c4e3102f35568d8628db16))

### Refactoring

- Break down query_graph into modular helper functions
  ([#672](https://github.com/n24q02m/better-code-review-graph/pull/672),
  [`c1c3c7c`](https://github.com/n24q02m/better-code-review-graph/commit/c1c3c7c0157005824bf099789603dbdba21a0219))

### Testing

- Add comprehensive coverage for temporal.py
  ([#675](https://github.com/n24q02m/better-code-review-graph/pull/675),
  [`7d0944e`](https://github.com/n24q02m/better-code-review-graph/commit/7d0944e2ed7f11610e17dd3df79606a47ad2dfa6))

- Add coverage for GraphStore.get_all_nodes
  ([#667](https://github.com/n24q02m/better-code-review-graph/pull/667),
  [`56f44d4`](https://github.com/n24q02m/better-code-review-graph/commit/56f44d42097cab8db9accec66dd5474fc1b352d1))

- Add coverage for search_edges_by_target_names
  ([#665](https://github.com/n24q02m/better-code-review-graph/pull/665),
  [`e91cf2a`](https://github.com/n24q02m/better-code-review-graph/commit/e91cf2acddeeb27845fa6e72908485301637f626))

- Reorganize and consolidate relay_setup tests
  ([#673](https://github.com/n24q02m/better-code-review-graph/pull/673),
  [`abce684`](https://github.com/n24q02m/better-code-review-graph/commit/abce6840c804c113d5fe7d621ea2564c8cff7f03))


## v3.17.2-beta.1 (2026-06-10)

### Bug Fixes

- Add Comparison section to README capability matrix
  ([#662](https://github.com/n24q02m/better-code-review-graph/pull/662),
  [`dcb08cd`](https://github.com/n24q02m/better-code-review-graph/commit/dcb08cd437a953dbc52b1a82428f1e134e40e143))

- Correct docs drift in tool count, semgrep rules, help topics, dead links
  ([#661](https://github.com/n24q02m/better-code-review-graph/pull/661),
  [`cdb4232`](https://github.com/n24q02m/better-code-review-graph/commit/cdb4232dd0c00ff871a0d027f6f4b0eca774873e))

### Chores

- **deps**: Lock file maintenance
  ([#659](https://github.com/n24q02m/better-code-review-graph/pull/659),
  [`9e5b7f0`](https://github.com/n24q02m/better-code-review-graph/commit/9e5b7f0b38482f5d6d745c48b51af892ec52396a))

- **deps**: Update step-security/harden-runner digest to 9af89fc
  ([#657](https://github.com/n24q02m/better-code-review-graph/pull/657),
  [`c6e35b4`](https://github.com/n24q02m/better-code-review-graph/commit/c6e35b4306ef25cafbcc43008ee17fb36c970fe9))


## v3.17.1 (2026-06-09)


## v3.17.1-beta.1 (2026-06-09)

### Bug Fixes

- Gitignore bot/merge junk artifacts (*.orig/*.rej/*.patch/*.diff/*.cover/*.bak)
  ([#627](https://github.com/n24q02m/better-code-review-graph/pull/627),
  [`30ea5d5`](https://github.com/n24q02m/better-code-review-graph/commit/30ea5d56effdbab87e7aba42faec9cc3bbae89b5))

### Chores

- **deps**: Lock file maintenance
  ([#631](https://github.com/n24q02m/better-code-review-graph/pull/631),
  [`1900f3b`](https://github.com/n24q02m/better-code-review-graph/commit/1900f3b40fb800d41129b2158b122bc27cb7eaad))

- **deps**: Update codecov/codecov-action action to v7
  ([#630](https://github.com/n24q02m/better-code-review-graph/pull/630),
  [`f19d46f`](https://github.com/n24q02m/better-code-review-graph/commit/f19d46f44420076b2ce6f05094672cababff4e79))


## v3.17.0 (2026-06-07)

### Bug Fixes

- Cover dev-version fallback via _resolve_version helper and update existing test
  ([#624](https://github.com/n24q02m/better-code-review-graph/pull/624),
  [`d366e41`](https://github.com/n24q02m/better-code-review-graph/commit/d366e41c291a48cc5262b9b95e12e65edc16196c))

- Report package version in serverInfo instead of fastmcp version
  ([#624](https://github.com/n24q02m/better-code-review-graph/pull/624),
  [`d366e41`](https://github.com/n24q02m/better-code-review-graph/commit/d366e41c291a48cc5262b9b95e12e65edc16196c))


## v3.17.0-beta.1 (2026-06-07)

### Bug Fixes

- Harden git subprocess calls against argument injection
  ([`fb33ce8`](https://github.com/n24q02m/better-code-review-graph/commit/fb33ce8dbd0c23d7de9d30c37147043b3b9185be))

- Prevent bare-name fallback pulling wrong edges in importers_of and tests_for
  ([`864757c`](https://github.com/n24q02m/better-code-review-graph/commit/864757cb3d0e13d87583e0536b434884277a8748))

- Prevent path traversal in export_graph_dispatch output_path
  ([`5f91325`](https://github.com/n24q02m/better-code-review-graph/commit/5f9132502ddb64b4cfc890ee30ac15aa1d5c92ba))

- Remove unused SupportedLanguage import in parser
  ([`452f940`](https://github.com/n24q02m/better-code-review-graph/commit/452f940228d8343a7d2ada93ee3c389f8d195296))

- Update actions/checkout digest to df4cb1c
  ([`548d4c5`](https://github.com/n24q02m/better-code-review-graph/commit/548d4c580ff2c33e82fd7ba12a2e7b2307ba530c))

- Update github/codeql-action digest to dd903d2
  ([`ad417df`](https://github.com/n24q02m/better-code-review-graph/commit/ad417df4a0727fa7fdd0ba7cf22306297f2df141))

### Features

- Add coverage tests for _handle_not_found
  ([`78fc047`](https://github.com/n24q02m/better-code-review-graph/commit/78fc04785e8d23c1e1ded52563f1a0a6677bf9d4))

- Add exception coverage test for parse_bytes in renamed_in_diff
  ([`e223694`](https://github.com/n24q02m/better-code-review-graph/commit/e22369475dbd5b1fdcb44cb85a9fe38b6d94a94e))

- Add OSError coverage test for renamed_in_diff path resolution
  ([`a317dd9`](https://github.com/n24q02m/better-code-review-graph/commit/a317dd9200007e499e7e78508b2fc4c26cc24112))

- Add OSError coverage tests for get_review_context and spot_check
  ([`cd99df0`](https://github.com/n24q02m/better-code-review-graph/commit/cd99df04e324f0bc0205aaf7033d61d8d49194f1))

- Add path resolution fallback coverage tests
  ([`48a98a0`](https://github.com/n24q02m/better-code-review-graph/commit/48a98a066bbaa6d14a5b9a62f3b7bce9593c2387))

- Add unit tests for _estimate_payload_bytes
  ([`717ce7f`](https://github.com/n24q02m/better-code-review-graph/commit/717ce7f188aa9345f80d219331cf85dae43bfd6a))

- Add unit tests for _lookup_node_directly
  ([`59b20fb`](https://github.com/n24q02m/better-code-review-graph/commit/59b20fb8e0f1ad288088f54ee071ded836338ecf))

- Add unit tests for _resolve_search_candidates
  ([`a160075`](https://github.com/n24q02m/better-code-review-graph/commit/a160075ba9401fc50802053f381f76e5bb9699cb))

- Add unit tests for _semgrep_executable helper
  ([`d8671a2`](https://github.com/n24q02m/better-code-review-graph/commit/d8671a20ca890d91e36d6e2115e62f54842782da))


## v3.16.4 (2026-06-01)

### Bug Fixes

- Pin mcp-core 1.17.2 (stable)
  ([`20b04bc`](https://github.com/n24q02m/better-code-review-graph/commit/20b04bcf62488a17b093ed41beb40c855b34c476))


## v3.16.4-beta.1 (2026-06-01)

### Bug Fixes

- Bump mcp-core to 1.17.2-beta.1 for beta testing
  ([`dc12a55`](https://github.com/n24q02m/better-code-review-graph/commit/dc12a5589cdc458855659520959f3751aacdf263))

- Repoint dead docs/setup-manual.md link to hosted setup guide
  ([#551](https://github.com/n24q02m/better-code-review-graph/pull/551),
  [`23bdcf1`](https://github.com/n24q02m/better-code-review-graph/commit/23bdcf175f31dd8bc96f58d87cbd3f385664799e))

- Sync docs to actual 6-tool surface and config/help actions
  ([#550](https://github.com/n24q02m/better-code-review-graph/pull/550),
  [`feb1a11`](https://github.com/n24q02m/better-code-review-graph/commit/feb1a115db57fa56df2012cdeb3004f97f201deb))

- Use defusedxml to prevent XXE in XML parsing
  ([#546](https://github.com/n24q02m/better-code-review-graph/pull/546),
  [`c7c0678`](https://github.com/n24q02m/better-code-review-graph/commit/c7c0678935a4423c3707aa3fde50bdfa5c864be7))


## v3.16.3 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.1 (BearerMCPApp resource_metadata #260)
  ([`24edb45`](https://github.com/n24q02m/better-code-review-graph/commit/24edb45bd641b3a08d8d23eb89b3f94eebaf12da))


## v3.16.2 (2026-05-29)

### Bug Fixes

- Pin mcp-core 1.17.0 (stable OAuth refresh_token)
  ([`f201731`](https://github.com/n24q02m/better-code-review-graph/commit/f2017310b045cea9ea6d760a57685a77e7583eb2))


## v3.16.2-beta.1 (2026-05-29)

### Bug Fixes

- Add get_review_context no-diff edge case tests
  ([#528](https://github.com/n24q02m/better-code-review-graph/pull/528),
  [`5894c24`](https://github.com/n24q02m/better-code-review-graph/commit/5894c246b76c89bd7abf50bb26741a7503282b9e))

- Add list_graph_stats coverage tests
  ([#524](https://github.com/n24q02m/better-code-review-graph/pull/524),
  [`ab9a319`](https://github.com/n24q02m/better-code-review-graph/commit/ab9a31980a8ab82183217f0e80a5d071c24adb4d))

- Bump mcp-core to 1.17.0-beta.1 for OAuth refresh_token
  ([`9fccdd0`](https://github.com/n24q02m/better-code-review-graph/commit/9fccdd034973cc5246d96f826dde23b4ad42e874))

- Correct stale tool names in SessionStart hook guidance
  ([#539](https://github.com/n24q02m/better-code-review-graph/pull/539),
  [`9cfb922`](https://github.com/n24q02m/better-code-review-graph/commit/9cfb92249f31ff11611c897ab5a44a27b9351c49))

- Prevent SQL injection in alter table column execution
  ([#520](https://github.com/n24q02m/better-code-review-graph/pull/520),
  [`9d9da03`](https://github.com/n24q02m/better-code-review-graph/commit/9d9da035c0b8aeef610a3af6ce16ddb7b5664634))

- Prevent SQL injection in temporal table creation
  ([#523](https://github.com/n24q02m/better-code-review-graph/pull/523),
  [`a40f8f3`](https://github.com/n24q02m/better-code-review-graph/commit/a40f8f3d093fe0cb5f1945942e9e72c94b5d41e3))

### Testing

- Add unit tests for list_graph_stats tool
  ([#524](https://github.com/n24q02m/better-code-review-graph/pull/524),
  [`ab9a319`](https://github.com/n24q02m/better-code-review-graph/commit/ab9a31980a8ab82183217f0e80a5d071c24adb4d))


## v3.16.1 (2026-05-28)

### Bug Fixes

- Drop local path source for mcp-core to align with PyPI-only pattern
  ([`6c2664d`](https://github.com/n24q02m/better-code-review-graph/commit/6c2664d63aa3b97d969662e31d47a3a16a450cad))

- Resolve ty 0.0.40 type errors and align list_kinds test with cursor iteration
  ([`6154f08`](https://github.com/n24q02m/better-code-review-graph/commit/6154f08cb7a3fb19933ca04394a4ab0fa1f32d81))

- Ruff format graph.py and tools.py to satisfy CI
  ([`a0e44df`](https://github.com/n24q02m/better-code-review-graph/commit/a0e44df134caba79f571ca26b9d1916485692008))


## v3.16.1-beta.1 (2026-05-28)

### Bug Fixes

- **deps**: Cap semgrep to <1.162 to avoid mcp==1.23.3 transitive pin conflict
  ([`f29b5a0`](https://github.com/n24q02m/better-code-review-graph/commit/f29b5a0fcc6b7d5e367e72796803a91a91669986))

- **deps**: Update non-major dependencies
  ([#513](https://github.com/n24q02m/better-code-review-graph/pull/513),
  [`c33936d`](https://github.com/n24q02m/better-code-review-graph/commit/c33936d2d7620f4dc75949acb974485a6d10f3b3))

### Performance Improvements

- Replace fetchall() with direct cursor iteration
  ([#514](https://github.com/n24q02m/better-code-review-graph/pull/514),
  [`c9741ab`](https://github.com/n24q02m/better-code-review-graph/commit/c9741ab43a16733dcc2653f1e8f3a44f33cbf55d))


## v3.16.0 (2026-05-26)

### Bug Fixes

- **deps**: Update dependency cohere to v7
  ([#509](https://github.com/n24q02m/better-code-review-graph/pull/509),
  [`0209d0d`](https://github.com/n24q02m/better-code-review-graph/commit/0209d0de01080e0f938fb47368ac86dfa1d65d4b))

### Chores

- **deps**: Update github/codeql-action digest to 03e4368
  ([#504](https://github.com/n24q02m/better-code-review-graph/pull/504),
  [`8c3c19a`](https://github.com/n24q02m/better-code-review-graph/commit/8c3c19aaa6d27afd2281bd41b2d091c073a8cbc6))

- **deps**: Update python:3.13-slim-bookworm docker digest to e4fa1f9
  ([#505](https://github.com/n24q02m/better-code-review-graph/pull/505),
  [`b968a27`](https://github.com/n24q02m/better-code-review-graph/commit/b968a27490eecae08876cf452d8ac34b5b400e19))


## v3.16.0-beta.4 (2026-05-24)

### Bug Fixes

- **deps**: Regenerate uv.lock with UV_NO_SOURCES for Docker compatibility
  ([`183fa97`](https://github.com/n24q02m/better-code-review-graph/commit/183fa97508d2dec5a8737ee260d98a0f37016f35))


## v3.16.0-beta.3 (2026-05-24)

### Bug Fixes

- Optimize SQLite kind filter, batch checks, harden security
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

- **deps**: Bump urllib3 to 2.7.0 + idna to 3.16 (Dependabot security alerts)
  ([`eb4655d`](https://github.com/n24q02m/better-code-review-graph/commit/eb4655df4c2aa74c64fa68aabb670b307d8f5388))

- **deps**: Update dependency google-genai to v2
  ([#485](https://github.com/n24q02m/better-code-review-graph/pull/485),
  [`948449f`](https://github.com/n24q02m/better-code-review-graph/commit/948449fdb447f6ede4ba276193b6c3bbdf559c51))

### Chores

- **deps**: Bump runtime + workflow pins from open Renovate PRs
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

- **deps**: Update actions/create-github-app-token digest to bcd2ba4
  ([#487](https://github.com/n24q02m/better-code-review-graph/pull/487),
  [`0166188`](https://github.com/n24q02m/better-code-review-graph/commit/01661888cb140aeee8e72b30efc380ca0f6f35ea))

- **deps**: Update codecov/codecov-action digest to e79a696
  ([#497](https://github.com/n24q02m/better-code-review-graph/pull/497),
  [`e89384e`](https://github.com/n24q02m/better-code-review-graph/commit/e89384ee48844dfcd11c3b6ce76541236c161354))

- **deps**: Update docker/build-push-action digest to f9f3042
  ([#498](https://github.com/n24q02m/better-code-review-graph/pull/498),
  [`a6a221e`](https://github.com/n24q02m/better-code-review-graph/commit/a6a221e0c5fa14e692b1b3b65e9ef17c32f0b7a2))

- **deps**: Update docker/login-action digest to 650006c
  ([#499](https://github.com/n24q02m/better-code-review-graph/pull/499),
  [`673408f`](https://github.com/n24q02m/better-code-review-graph/commit/673408f9797809ffb7e74f639e71f7f841bbfaa8))

- **deps**: Update docker/setup-buildx-action digest to d7f5e7f
  ([#502](https://github.com/n24q02m/better-code-review-graph/pull/502),
  [`c871a77`](https://github.com/n24q02m/better-code-review-graph/commit/c871a77fff8074ed77e74e3cc983c77dc0b0aeab))

- **deps**: Update github/codeql-action digest to 458d36d
  ([#489](https://github.com/n24q02m/better-code-review-graph/pull/489),
  [`e6c48df`](https://github.com/n24q02m/better-code-review-graph/commit/e6c48df8bc8aa34e45415624a2c92f426e2532a0))

- **deps**: Update step-security/harden-runner digest to ab7a940
  ([#490](https://github.com/n24q02m/better-code-review-graph/pull/490),
  [`09aa29c`](https://github.com/n24q02m/better-code-review-graph/commit/09aa29c455344913ceb0a62909ccfd26a028ddbd))

### Performance Improvements

- **graph**: Push edge kind filter into SQLite + batch repo/survival lookups
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))

### Testing

- Cover kind filter, batched lookups, security_scan batching
  ([#496](https://github.com/n24q02m/better-code-review-graph/pull/496),
  [`483d1ce`](https://github.com/n24q02m/better-code-review-graph/commit/483d1ce318168c048abe9d2f5f641b98d6d0d45c))


## v3.16.0-beta.2 (2026-05-10)

### Bug Fixes

- Copy migrations/ + rules/ into Docker builder for Hatch force-include
  ([#482](https://github.com/n24q02m/better-code-review-graph/pull/482),
  [`5ee20be`](https://github.com/n24q02m/better-code-review-graph/commit/5ee20bebf1bb61e7c05bece87aa492f8620f3a96))


## v3.16.0-beta.1 (2026-05-10)

### Bug Fixes

- Bump python-multipart to 0.0.27 to patch CVE-2026-42561 (DoS via unbounded multipart headers)
  ([#452](https://github.com/n24q02m/better-code-review-graph/pull/452),
  [`e831beb`](https://github.com/n24q02m/better-code-review-graph/commit/e831beb741d33a077447bd7b67ef01c87ae4eaf1))

- Document cross-repo federation in help topics
  ([#464](https://github.com/n24q02m/better-code-review-graph/pull/464),
  [`e803603`](https://github.com/n24q02m/better-code-review-graph/commit/e80360353ee3b757dd3d47b54c03605e65343f77))

- Document security tool + temporal tracking + breaking migration
  ([#480](https://github.com/n24q02m/better-code-review-graph/pull/480),
  [`70dde4e`](https://github.com/n24q02m/better-code-review-graph/commit/70dde4e0cf3d48e0051fc8b3c243796f97b5649a))

- Forward target_repos in federated build + 3-repo smoke fixture
  ([#469](https://github.com/n24q02m/better-code-review-graph/pull/469),
  [`aa70484`](https://github.com/n24q02m/better-code-review-graph/commit/aa7048407cb5c7b882776a7553763f0e30cc9130))

- Harden alembic resolver + tests for installed-mode + future-revision + parity gates
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- Pre-2.0 release smoke + breaking-change announcement banner
  ([#481](https://github.com/n24q02m/better-code-review-graph/pull/481),
  [`2b9e97b`](https://github.com/n24q02m/better-code-review-graph/commit/2b9e97b869c12dbce09e83b62ed17394821cdd45))

- Regenerate uv.lock without [tool.uv.sources] directory pin
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Regenerate uv.lock without directory pin (Task 4)
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Regex in 005_temporal_columns must consume exactly 3 slashes
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- **deps**: Update dependency google-genai to v2
  ([#468](https://github.com/n24q02m/better-code-review-graph/pull/468),
  [`ab08f4d`](https://github.com/n24q02m/better-code-review-graph/commit/ab08f4dfaf53822a907a40232cfe665e954cd653))

### Chores

- **deps**: Update actions/dependency-review-action action to v5
  ([#467](https://github.com/n24q02m/better-code-review-graph/pull/467),
  [`e96a9d1`](https://github.com/n24q02m/better-code-review-graph/commit/e96a9d1e1cc40649135a63f332acfff992843762))

- **deps**: Update github/codeql-action digest to 7fd177f
  ([#451](https://github.com/n24q02m/better-code-review-graph/pull/451),
  [`864fe77`](https://github.com/n24q02m/better-code-review-graph/commit/864fe772e3efb57b133588af2284965b7dc65591))

- **deps**: Update python:3.13-slim-bookworm docker digest to 386df64
  ([#465](https://github.com/n24q02m/better-code-review-graph/pull/465),
  [`0da0ff1`](https://github.com/n24q02m/better-code-review-graph/commit/0da0ff158a1390598e3a6912230822431f1f2e90))

### Features

- Alembic 003_federation — add repo_id + repos table for cross-repo scoping
  ([#454](https://github.com/n24q02m/better-code-review-graph/pull/454),
  [`c1c7bd8`](https://github.com/n24q02m/better-code-review-graph/commit/c1c7bd8b2060ff23a7671097a26797cfb444a421))

- Alembic 004_security_tags — add nullable security_tags JSON column
  ([#471](https://github.com/n24q02m/better-code-review-graph/pull/471),
  [`004355b`](https://github.com/n24q02m/better-code-review-graph/commit/004355babe8923e135da6f37cdfe2e130c045831))

- Alembic 005_temporal_columns — BREAKING add valid_from_sha/valid_to_sha
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- Alembic 006_commits_table + first-parent backfill
  ([#476](https://github.com/n24q02m/better-code-review-graph/pull/476),
  [`9d824f0`](https://github.com/n24q02m/better-code-review-graph/commit/9d824f04dfd12216de8e1c148ab65125310afdca))

- Alembic baseline + Phase 1 summary columns recorded as 001_baseline + 002_summary_columns
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- As_of + diff cross-cutting params on query + review
  ([#478](https://github.com/n24q02m/better-code-review-graph/pull/478),
  [`ec0d059`](https://github.com/n24q02m/better-code-review-graph/commit/ec0d05941044d961fae4d4de8008da146bcb4ea0))

- Backup graph.db to .pre-2.0.bak before BREAKING 005_temporal_columns migration
  ([#470](https://github.com/n24q02m/better-code-review-graph/pull/470),
  [`e4ee8b9`](https://github.com/n24q02m/better-code-review-graph/commit/e4ee8b9105172372fc8361bc2aa0674aecb8e7c4))

- Cross-cutting repo param on query + review actions
  ([#463](https://github.com/n24q02m/better-code-review-graph/pull/463),
  [`093101b`](https://github.com/n24q02m/better-code-review-graph/commit/093101b6d8fa2f98a70c563668e6f1dbd32a59a1))

- Cross-repo resolver dispatcher + fallback for tier-2 languages
  ([#461](https://github.com/n24q02m/better-code-review-graph/pull/461),
  [`a09510c`](https://github.com/n24q02m/better-code-review-graph/commit/a09510cba2e823953cfa55411ccb6fb71bd65e98))

- Go cross-repo resolver -- go.mod replace + go.work workspaces
  ([#458](https://github.com/n24q02m/better-code-review-graph/pull/458),
  [`e5a41d3`](https://github.com/n24q02m/better-code-review-graph/commit/e5a41d3ae8c3f755afc0dc6a75ab676411cff296))

- Java cross-repo resolver -- maven modules + gradle include parsing
  ([#460](https://github.com/n24q02m/better-code-review-graph/pull/460),
  [`5901ca2`](https://github.com/n24q02m/better-code-review-graph/commit/5901ca2140821def70e96037ad06d92fe9e4ae74))

- Parser + incremental — populate repo_id and refresh repos.last_indexed_sha
  ([#462](https://github.com/n24q02m/better-code-review-graph/pull/462),
  [`c8fb4e8`](https://github.com/n24q02m/better-code-review-graph/commit/c8fb4e8acb1b0e3bfd9ff356ad823d8916feb060))

- Phase 2 Task 0 — alembic baseline + Phase 1 summary stamp target
  ([#453](https://github.com/n24q02m/better-code-review-graph/pull/453),
  [`bd23e90`](https://github.com/n24q02m/better-code-review-graph/commit/bd23e90bcd8f063f9eddbfe5b5ee8c397c38dba0))

- Phase 3 Task 3 — tier-1 heuristic security scanner
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Phase 3 Task 4 — Semgrep tier-2 security engine ([security] extra)
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Phase 3 Task 6 — alembic 005_temporal_columns BREAKING (valid_from_sha + valid_to_sha)
  ([#475](https://github.com/n24q02m/better-code-review-graph/pull/475),
  [`3a44f1d`](https://github.com/n24q02m/better-code-review-graph/commit/3a44f1d6c340682070eaaced8f5525438728d409))

- Python cross-repo resolver — pyproject.toml deps + namespace package walk
  ([#456](https://github.com/n24q02m/better-code-review-graph/pull/456),
  [`815a1a5`](https://github.com/n24q02m/better-code-review-graph/commit/815a1a5d7150a5471fae51df9456e5228dcc3b4d))

- RepoRegistry path-derived repo_id with deterministic id derivation
  ([#455](https://github.com/n24q02m/better-code-review-graph/pull/455),
  [`9e63050`](https://github.com/n24q02m/better-code-review-graph/commit/9e630505ed0ec7a148cfe1f3e153bcaf209ee288))

- Review.delta show_line_shifts mode for refactor auditing (#320)
  ([#479](https://github.com/n24q02m/better-code-review-graph/pull/479),
  [`989880c`](https://github.com/n24q02m/better-code-review-graph/commit/989880c76434656fe96ffae1589396754b4c1987))

- Rust cross-repo resolver -- Cargo.toml path deps + workspace members
  ([#459](https://github.com/n24q02m/better-code-review-graph/pull/459),
  [`fadaae6`](https://github.com/n24q02m/better-code-review-graph/commit/fadaae65151e1258dcb1fb73eb3b445974b24f17))

- Security MCP tool — scan/report/suppress/rule_list actions
  ([#474](https://github.com/n24q02m/better-code-review-graph/pull/474),
  [`3e347df`](https://github.com/n24q02m/better-code-review-graph/commit/3e347dfad0ef71ad51fb1ea574ca5d4f9138a51d))

- TemporalIndex — close-out + supersede logic for nodes/edges across commits
  ([#477](https://github.com/n24q02m/better-code-review-graph/pull/477),
  [`43ef41d`](https://github.com/n24q02m/better-code-review-graph/commit/43ef41d455d2b1229ecc7ec3b947d3ec56ecd47b))

- Tier-1 heuristic security scanner -- 5 rules covering OWASP top sinks
  ([#472](https://github.com/n24q02m/better-code-review-graph/pull/472),
  [`57a77eb`](https://github.com/n24q02m/better-code-review-graph/commit/57a77eb8b369133b34f139072b5cbd559ffcb175))

- Tier-2 semgrep security engine via [security] extra — opt-in install
  ([#473](https://github.com/n24q02m/better-code-review-graph/pull/473),
  [`1f399cc`](https://github.com/n24q02m/better-code-review-graph/commit/1f399cc95953118452cde2255501fd5961a8664b))

- Typescript cross-repo resolver — tsconfig paths + package.json workspaces
  ([#457](https://github.com/n24q02m/better-code-review-graph/pull/457),
  [`02b3346`](https://github.com/n24q02m/better-code-review-graph/commit/02b3346003ed2f7b66bb189836265f8bb5a10314))


## v3.15.1 (2026-05-09)


## v3.15.1-beta.2 (2026-05-08)

### Bug Fixes

- Regenerate uv.lock without [tool.uv.sources] for Docker build
  ([`de9567d`](https://github.com/n24q02m/better-code-review-graph/commit/de9567d385fc0daf5d16601c3963ff82808aa52d))


## v3.15.1-beta.1 (2026-05-08)

### Bug Fixes

- Ruff import sort + format on incremental.py for CI green
  ([`96a7d17`](https://github.com/n24q02m/better-code-review-graph/commit/96a7d17ebffe00d61520eb946f074045bda7e04e))


## v3.15.0 (2026-05-08)


## v3.15.0-beta.1 (2026-05-08)

### Bug Fixes

- Batch-load callers via WHERE IN to fix N+1 query
  ([`955df3f`](https://github.com/n24q02m/better-code-review-graph/commit/955df3f33ae556f87d3efa20f7dd5cda3fa79f1b))

- Dual-cache _filter_valid_paths for fewer OS resolve calls
  ([`e57bbd1`](https://github.com/n24q02m/better-code-review-graph/commit/e57bbd1900346adf4cbe2f74c66298d617028885))

- Prevent path traversal in _sub_data_dir credential storage
  ([`4039c9f`](https://github.com/n24q02m/better-code-review-graph/commit/4039c9f83cb65801c2366586bff37034522c2383))

- Reduce complexity of _handle_solidity_node via helper extraction
  ([`cf67f74`](https://github.com/n24q02m/better-code-review-graph/commit/cf67f74e75aed341c9146823e13dfe2ac0824ed8))

- Reduce complexity of _resolve_query_target via early returns
  ([`940c36b`](https://github.com/n24q02m/better-code-review-graph/commit/940c36b00ad7fa2d446d30fe99e09ec5fbc11f17))

- Reduce complexity of incremental_update via helper extraction
  ([`3f48caf`](https://github.com/n24q02m/better-code-review-graph/commit/3f48cafeddafec2b8718e18337e1e3ddeb6be14d))

- Remove unused 'from __future__ import annotations' in graph.py
  ([`dc9cef6`](https://github.com/n24q02m/better-code-review-graph/commit/dc9cef6dd4d5fc5cdf6e9dfcff0760637afb6425))

- Remove unused 'from __future__ import annotations' in relay_schema.py
  ([`18e3b75`](https://github.com/n24q02m/better-code-review-graph/commit/18e3b75a72376a21c4575d0950387c603ea15ea5))

- Remove unused 'from __future__ import annotations' in tools.py
  ([`2866cfc`](https://github.com/n24q02m/better-code-review-graph/commit/2866cfc7f835983b555a62b4944f43c2aa7f3995))

- Stream edges from sqlite instead of loading entire table in _build_networkx_graph
  ([`bea89d7`](https://github.com/n24q02m/better-code-review-graph/commit/bea89d7046fdfc1e107745fc940653fabe82690a))

- **deps**: Bump n24q02m-mcp-core to >=1.14.0 + qwen3-embed to >=1.9.2
  ([`634fee2`](https://github.com/n24q02m/better-code-review-graph/commit/634fee26c0e86d9506289171ed16d9db2fceddd9))

### Features

- Add error path test for _list_kinds_in_graph
  ([`966d94a`](https://github.com/n24q02m/better-code-review-graph/commit/966d94aa74629ac2bd9c0048b2770dce4e83dea0))

- Add error path test for get_docs_section store initialization
  ([`778d340`](https://github.com/n24q02m/better-code-review-graph/commit/778d340d6a3fd3629c70ab184dc5c7d121c744b4))

- Add error path test for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))

- Add legacy-DB migration + idempotency tests for summary columns
  ([`d65eddd`](https://github.com/n24q02m/better-code-review-graph/commit/d65eddd79d8d36493ebf82a0779dbf124250f249))

- Add summary/summary_provider/source_hash columns to nodes for Phase 1 LLM summaries
  ([`04b9df9`](https://github.com/n24q02m/better-code-review-graph/commit/04b9df967554a97157261fd27f70b9b4c0faf35a))

- Add Table of contents heading + auto-generated link list (Spec E Wave 2)
  ([`d1133bc`](https://github.com/n24q02m/better-code-review-graph/commit/d1133bc742729ced7cb5cc2cf844d9a8f360d497))

- Add tests for get_nodes_by_files batch fetch
  ([`cfb2fde`](https://github.com/n24q02m/better-code-review-graph/commit/cfb2fde700a72100bbd4de7c79934bf930ed44f9))

- Batch_summarize with source_hash cache + cost cap + per-node error tolerance
  ([`fdc7664`](https://github.com/n24q02m/better-code-review-graph/commit/fdc7664e629c76ba6cf17432eb8254f21b81c62a))

- Close coverage gaps in export_graph_dispatch + exporter formatters
  ([`e655ec0`](https://github.com/n24q02m/better-code-review-graph/commit/e655ec0590043fff47908cd61d5cce004059516a))

- Document graph.export + graph.summarize in help topic + README v1.6 callout
  ([`a656567`](https://github.com/n24q02m/better-code-review-graph/commit/a65656735b98506630585f18c15d62770e9244dd))

- Graph(action='export') with graphml + json-ld + dot + cypher formats
  ([`aaa1f08`](https://github.com/n24q02m/better-code-review-graph/commit/aaa1f0880ef9e73bc1c5d9b406dbd93302710f28))

- Harden summarize_node against empty SDK responses + brace-safe prompt
  ([`e63cb6c`](https://github.com/n24q02m/better-code-review-graph/commit/e63cb6c7a9331450dc471590216cff6de882f46c))

- Link to mcp.n24q02m.com unified docs site (Spec F Phase 4)
  ([`d13d104`](https://github.com/n24q02m/better-code-review-graph/commit/d13d1047c77b5a6f7997c6c37d09a3551fdf53a9))

- Lock empty-string + unicode + frozen contracts in summarizer tests
  ([`8dcac22`](https://github.com/n24q02m/better-code-review-graph/commit/8dcac22034c7d228e146fa201470566aa3d7c870))

- Lock per-node persistence + empty-string cache-miss contracts in batch tests
  ([`310d287`](https://github.com/n24q02m/better-code-review-graph/commit/310d2873e8b3c3fdf0aeeedb083f259a165e7b4f))

- Parser populates Function source_text + upsert_node persists it
  ([`79cb3bf`](https://github.com/n24q02m/better-code-review-graph/commit/79cb3bf553cc6fbad0c6337597f235b36df0544b))

- Summarize_node single-node LLM summary via Gemini or OpenAI
  ([`a90f17c`](https://github.com/n24q02m/better-code-review-graph/commit/a90f17ceaa957f41991390a86d0facd91a50fc71))

- Summarizer cache key derivation + provider env-var detection
  ([`22b446e`](https://github.com/n24q02m/better-code-review-graph/commit/22b446e7c8227b5c95384dd058d571b2ec82022e))

- Sync cross-promo section ([#449](https://github.com/n24q02m/better-code-review-graph/pull/449),
  [`8534ffe`](https://github.com/n24q02m/better-code-review-graph/commit/8534ffeee80019a567478cb6a54c117c52f29895))

- Wire graph(action='summarize') MCP action with cost cap + provider auto-detect
  ([`a1c2182`](https://github.com/n24q02m/better-code-review-graph/commit/a1c218263439c0c926abc0523d67643d440cf141))

### Testing

- Add error path coverage for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))

- Add robust error path coverage for graph build/update
  ([`89dd791`](https://github.com/n24q02m/better-code-review-graph/commit/89dd791a219bf67d15570d79474e6cd1439fe287))


## v3.14.0 (2026-05-06)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES for Docker build
  ([`986bbde`](https://github.com/n24q02m/better-code-review-graph/commit/986bbde219ede531ca9041e1932afc34b5f21d03))


## v3.14.0-beta.1 (2026-05-06)

### Bug Fixes

- Consolidate setup docs body to 3 methods (drop legacy Method 4/5)
  ([#421](https://github.com/n24q02m/better-code-review-graph/pull/421),
  [`8337cd5`](https://github.com/n24q02m/better-code-review-graph/commit/8337cd5a1c6d673dd6a258e7014839ce45840d39))

- Restore test coverage above 95% threshold for v1.7 features
  ([`572f474`](https://github.com/n24q02m/better-code-review-graph/commit/572f474543235a80c66887afd986ec7ea91c89ad))

- **deps**: Update non-major dependencies
  ([#428](https://github.com/n24q02m/better-code-review-graph/pull/428),
  [`5588988`](https://github.com/n24q02m/better-code-review-graph/commit/5588988c2ddfe004e8b5b06cf7b52804058903c8))

### Chores

- **deps**: Update step-security/harden-runner digest to a5ad31d
  ([#412](https://github.com/n24q02m/better-code-review-graph/pull/412),
  [`2bd88d1`](https://github.com/n24q02m/better-code-review-graph/commit/2bd88d18d36104b5a035cfa42162dbcccbdc6748))

### Features

- Add embeddings_count + keyword_only to query/search response header
  ([`14355be`](https://github.com/n24q02m/better-code-review-graph/commit/14355be4d6dfa23c9de2ca74ced2005ea8476cc0))

- Add explicit Method overview section to setup docs
  ([#420](https://github.com/n24q02m/better-code-review-graph/pull/420),
  [`691ee39`](https://github.com/n24q02m/better-code-review-graph/commit/691ee39da8847c3328cd49e77b2b335d8f6399a8))

- Add query.renamed_in_diff for symbol callsite line drift vs base ref
  ([`3e1511c`](https://github.com/n24q02m/better-code-review-graph/commit/3e1511c50cf29d60c23bccf0f6879e04de3c08d6))

- Add query.spot_check action for random callsite source samples
  ([`54bdc5a`](https://github.com/n24q02m/better-code-review-graph/commit/54bdc5ae00b2def861e6565dba4d96021e0aff98))

- Add recipes topic to help with stage-mapped operational patterns
  ([`1b6a9cf`](https://github.com/n24q02m/better-code-review-graph/commit/1b6a9cf09b13fbf5d1374771ddf51f5cd0c1595c))

- Add reviewer_summary to graph update response
  ([`8e4d1e7`](https://github.com/n24q02m/better-code-review-graph/commit/8e4d1e72402c342a2c623d82af9c1c2629d8deef))

- Align userConfig with relay_schema fields
  ([#425](https://github.com/n24q02m/better-code-review-graph/pull/425),
  [`916d7e9`](https://github.com/n24q02m/better-code-review-graph/commit/916d7e95a095685b8bea6ee0a156047e6659757b))

- Auto-pick Function over File for callers_of/callees_of bare-name
  ([`dc22290`](https://github.com/n24q02m/better-code-review-graph/commit/dc222908fa277c37fbf33502edb1d9fa24712c5b))

- Auto-truncate impact response when payload exceeds size cap
  ([`030faef`](https://github.com/n24q02m/better-code-review-graph/commit/030faef605631c238f27006a9b1e9c5366b2632f))

- Declare userConfig schema and document install prompt
  ([#422](https://github.com/n24q02m/better-code-review-graph/pull/422),
  [`ca6f34d`](https://github.com/n24q02m/better-code-review-graph/commit/ca6f34d08e31477609a719558ebefc8606f4328d))

- Document userConfig credential prompts per plugin
  ([#426](https://github.com/n24q02m/better-code-review-graph/pull/426),
  [`83c9d04`](https://github.com/n24q02m/better-code-review-graph/commit/83c9d0418df2033a7474015b482f195cc9dc3e50))

- Note CC scope-by-endpoint mutual exclusivity rule
  ([#427](https://github.com/n24q02m/better-code-review-graph/pull/427),
  [`a8a8596`](https://github.com/n24q02m/better-code-review-graph/commit/a8a8596ebd9931fde3d61f1c60561089989021c8))

- Surface dynamic-dispatch hints in callers_of/callees_of response
  ([`6e60644`](https://github.com/n24q02m/better-code-review-graph/commit/6e606448137f8206429e0586b2a13851724bf7db))

- Warn at search when keyword fallback meets phrase-shape query
  ([`427770f`](https://github.com/n24q02m/better-code-review-graph/commit/427770f0591d91319acecc7b51153c6d6649a639))


## v3.13.0 (2026-05-04)

### Bug Fixes

- Bump mcp-core to 1.13.0 (STABLE)
  ([#419](https://github.com/n24q02m/better-code-review-graph/pull/419),
  [`34f2770`](https://github.com/n24q02m/better-code-review-graph/commit/34f2770f371f42072d29dbfc8912f3d8dad9087c))


## v3.13.0-beta.10 (2026-05-03)

### Features

- Bump mcp-core to 1.13.0-beta.7
  ([#414](https://github.com/n24q02m/better-code-review-graph/pull/414),
  [`7d5f70d`](https://github.com/n24q02m/better-code-review-graph/commit/7d5f70d10ae3e7214e3ae3eecaabbb2f82f9f97c))

- Document MCP_RELAY_PASSWORD edge auth gate
  ([#415](https://github.com/n24q02m/better-code-review-graph/pull/415),
  [`6457004`](https://github.com/n24q02m/better-code-review-graph/commit/6457004c225bcf3c47556e323809394e5a11951d))


## v3.13.0-beta.9 (2026-05-03)

### Bug Fixes

- HTTP multi-user credential wiring (per-sub contextvar)
  ([#413](https://github.com/n24q02m/better-code-review-graph/pull/413),
  [`4e77192`](https://github.com/n24q02m/better-code-review-graph/commit/4e771929f5216dd0da9e9b8e0be1d3f1f1859390))


## v3.13.0-beta.8 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock for new mcp-core beta (Docker trap)
  ([#411](https://github.com/n24q02m/better-code-review-graph/pull/411),
  [`04453e1`](https://github.com/n24q02m/better-code-review-graph/commit/04453e1ee9ea72f88917a0929fcc180dc64768e1))


## v3.13.0-beta.7 (2026-05-02)

### Bug Fixes

- Gate PerPluginStore fallback behind HTTP mode (stdio-pure spec §4.1)
  ([#410](https://github.com/n24q02m/better-code-review-graph/pull/410),
  [`7abeb4c`](https://github.com/n24q02m/better-code-review-graph/commit/7abeb4c96685f641a1f75f62c9a6b18b054aa22e))


## v3.13.0-beta.6 (2026-05-02)

### Bug Fixes

- Regenerate uv.lock UV_NO_SOURCES=1 (Docker build trap)
  ([#409](https://github.com/n24q02m/better-code-review-graph/pull/409),
  [`7119a0e`](https://github.com/n24q02m/better-code-review-graph/commit/7119a0e4cbfb85ac04854747f587625e9f5e4461))


## v3.13.0-beta.5 (2026-05-02)

### Bug Fixes

- Setup docs + README reflect stdio-pure architecture
  ([#408](https://github.com/n24q02m/better-code-review-graph/pull/408),
  [`39e4090`](https://github.com/n24q02m/better-code-review-graph/commit/39e40907a5b074b72f747e0b9dc1d191475f2a20))

- **deps**: Update non-major dependencies
  ([#403](https://github.com/n24q02m/better-code-review-graph/pull/403),
  [`bb8eedd`](https://github.com/n24q02m/better-code-review-graph/commit/bb8eedd25a94fa4dc79b8a74c8fa1dd6a36153ad))

### Chores

- **deps**: Update github/codeql-action digest to 0daab03
  ([#405](https://github.com/n24q02m/better-code-review-graph/pull/405),
  [`2ddaf8a`](https://github.com/n24q02m/better-code-review-graph/commit/2ddaf8a99e0bcc6fd699add76101a3483b2a0454))

### Features

- Stdio-pure + http-multi-user (drop daemon-bridge)
  ([#407](https://github.com/n24q02m/better-code-review-graph/pull/407),
  [`2cc52fd`](https://github.com/n24q02m/better-code-review-graph/commit/2cc52fd4917313c4f2cc10b333742e9fa306ea3c))


## v3.13.0-beta.4 (2026-04-30)

### Bug Fixes

- G6 UX status accuracy — derive state from live PerPluginStore
  ([#404](https://github.com/n24q02m/better-code-review-graph/pull/404),
  [`8d83382`](https://github.com/n24q02m/better-code-review-graph/commit/8d833828dc4e118875a3d3757c7bbe7bcf27cc18))

- Re-trigger CI after mcp-core lint+format fix
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))

- Ruff sort imports in test_per_plugin_storage_migration.py
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))

### Features

- **docs**: Add trust model section to README
  ([#401](https://github.com/n24q02m/better-code-review-graph/pull/401),
  [`d46bb32`](https://github.com/n24q02m/better-code-review-graph/commit/d46bb324f4dcae5bed5ed0d07036718b6d81a767))

- **storage**: Migrate to PerPluginStore from mcp-core 1.13.0b1+
  ([#402](https://github.com/n24q02m/better-code-review-graph/pull/402),
  [`68908d9`](https://github.com/n24q02m/better-code-review-graph/commit/68908d957e6ebde80ca6cdb3c6bbce5be62a289c))


## v3.13.0-beta.3 (2026-04-30)

### Bug Fixes

- Regenerate uv.lock with UV_NO_SOURCES=1 to remove local path references
  ([#399](https://github.com/n24q02m/better-code-review-graph/pull/399),
  [`f7381d3`](https://github.com/n24q02m/better-code-review-graph/commit/f7381d3c4940ed548c83a52fe2eae88f1fab14d1))


## v3.13.0-beta.2 (2026-04-30)

### Bug Fixes

- Strip [tool.uv.sources] in Dockerfile to fix uv sync --frozen Docker build
  ([#398](https://github.com/n24q02m/better-code-review-graph/pull/398),
  [`500b8bb`](https://github.com/n24q02m/better-code-review-graph/commit/500b8bb261be73c19b521226ce96b11d7382d548))


## v3.13.0-beta.1 (2026-04-30)

### Features

- Route stdio mode to FastMCP direct + multi-target Dockerfile
  ([#397](https://github.com/n24q02m/better-code-review-graph/pull/397),
  [`ba0f159`](https://github.com/n24q02m/better-code-review-graph/commit/ba0f1597b3bd5fb7c5c33d3e4dc8cf708bb3d23d))


## v3.12.5 (2026-04-29)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.11.3 for D17 tools cache refresh
  ([#394](https://github.com/n24q02m/better-code-review-graph/pull/394),
  [`3618982`](https://github.com/n24q02m/better-code-review-graph/commit/361898248a6bdfda8ad6d1c07b2135740994e2fc))


## v3.12.4 (2026-04-29)

### Bug Fixes

- Rebuild uv.lock without local path source
  ([#391](https://github.com/n24q02m/better-code-review-graph/pull/391),
  [`a6bac96`](https://github.com/n24q02m/better-code-review-graph/commit/a6bac963ef05c55311771429fce345f913e5413e))


## v3.12.3 (2026-04-29)

### Bug Fixes

- Not_found reason discriminator + languages filter (D15+D16, fixes #339 #340)
  ([#387](https://github.com/n24q02m/better-code-review-graph/pull/387),
  [`ec6654a`](https://github.com/n24q02m/better-code-review-graph/commit/ec6654ae466b5b8bd56ea9b1c85193b8bbdd873a))

- Register config__open_relay tool (Transparent Bridge Wave 3)
  ([#389](https://github.com/n24q02m/better-code-review-graph/pull/389),
  [`f03e9ed`](https://github.com/n24q02m/better-code-review-graph/commit/f03e9ed090865c2e296cb12c9de7a7a299f5bb8b))

- **deps**: Update dawidd6/action-send-mail action to v17
  ([#386](https://github.com/n24q02m/better-code-review-graph/pull/386),
  [`e51b99c`](https://github.com/n24q02m/better-code-review-graph/commit/e51b99c843acba6421c910d303da8b17cb3971ae))

- **deps**: Update non-major dependencies
  ([#385](https://github.com/n24q02m/better-code-review-graph/pull/385),
  [`225b3b3`](https://github.com/n24q02m/better-code-review-graph/commit/225b3b3f540a4559dc85300aeb16f3784d5a5c12))


## v3.12.2 (2026-04-28)

### Bug Fixes

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- Pass MCP_TRANSPORT=stdio in plugin.json + uv run --no-sync hooks
  ([#379](https://github.com/n24q02m/better-code-review-graph/pull/379),
  [`369e28a`](https://github.com/n24q02m/better-code-review-graph/commit/369e28ade1eb162490f5cb212a52433cf52bf1b6))

- **credentials**: Rip _share_cloud_keys_to_peers — per-server isolation
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- **deps**: Bump n24q02m-mcp-core to 1.10.0 — Transparent Bridge waves 1-3
  ([#382](https://github.com/n24q02m/better-code-review-graph/pull/382),
  [`6469340`](https://github.com/n24q02m/better-code-review-graph/commit/646934026f26efae500c80cb75e86f3eada3ba44))

- **lint**: Ruff format pass ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))

- **test**: Cover multi-user save_credentials + per-sub helpers (95% coverage)
  ([#380](https://github.com/n24q02m/better-code-review-graph/pull/380),
  [`8706fa1`](https://github.com/n24q02m/better-code-review-graph/commit/8706fa14ce5a9aa992eebef6f8c7d6cf095cb0ff))


## v3.12.1 (2026-04-28)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.9.0
  ([#378](https://github.com/n24q02m/better-code-review-graph/pull/378),
  [`23a8526`](https://github.com/n24q02m/better-code-review-graph/commit/23a85263df6826176142453ddb1a25340a521e7e))

- **deps**: Update dependency qwen3-embed to >=1.9.1
  ([#374](https://github.com/n24q02m/better-code-review-graph/pull/374),
  [`edddd98`](https://github.com/n24q02m/better-code-review-graph/commit/edddd987fed0b12a6d9af700fae81f3c8d0873c1))


## v3.12.0 (2026-04-27)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.8.1
  ([#371](https://github.com/n24q02m/better-code-review-graph/pull/371),
  [`39796de`](https://github.com/n24q02m/better-code-review-graph/commit/39796de0ea6b6840cd4d4dd579c69272d75128fc))

### Chores

- **deps**: Update dependency ruff to >=0.15.12
  ([#364](https://github.com/n24q02m/better-code-review-graph/pull/364),
  [`a521040`](https://github.com/n24q02m/better-code-review-graph/commit/a5210404e8dab8039d9a74f755594f32f49d0420))

### Features

- Add ## E2E section to CLAUDE.md per Task 21 docs rollout
  ([#368](https://github.com/n24q02m/better-code-review-graph/pull/368),
  [`a930474`](https://github.com/n24q02m/better-code-review-graph/commit/a9304743cf913277686782e3ce137ba3618bfce4))

### Performance Improvements

- **embeddings**: Optimize embedding insertions using executemany
  ([#366](https://github.com/n24q02m/better-code-review-graph/pull/366),
  [`0fcde8d`](https://github.com/n24q02m/better-code-review-graph/commit/0fcde8d1d525beb78454942eab0761e2e566059c))


## v3.12.0-beta.3 (2026-04-27)

### Bug Fixes

- Chown /app to appuser so runtime state dirs are writable
  ([`530dfb4`](https://github.com/n24q02m/better-code-review-graph/commit/530dfb4ae438c09e03d36a869d78d3c9f61110a7))


## v3.12.0-beta.2 (2026-04-27)

### Bug Fixes

- Copy src/ before uv sync so the project actually installs
  ([`19c21b2`](https://github.com/n24q02m/better-code-review-graph/commit/19c21b214bb13f6e7654f02f0fe37e7bbaba5dd9))


## v3.12.0-beta.1 (2026-04-27)

### Bug Fixes

- Sweep doppler/infisical refs to skret SSM
  ([`6c315c6`](https://github.com/n24q02m/better-code-review-graph/commit/6c315c6b8f3552b71f66e8972f338475e33b24b9))

### Features

- Crg per-JWT-sub graph DB + storage for multi-user remote
  ([#367](https://github.com/n24q02m/better-code-review-graph/pull/367),
  [`11c99bd`](https://github.com/n24q02m/better-code-review-graph/commit/11c99bd10e58aa1e2f38e9b862b380a2b91c4b1a))


## v3.11.1 (2026-04-24)

### Bug Fixes

- Regenerate uv.lock without [tool.uv.sources] for Docker build
  ([#363](https://github.com/n24q02m/better-code-review-graph/pull/363),
  [`70825bd`](https://github.com/n24q02m/better-code-review-graph/commit/70825bd21a6b3c5e2c3a6385faa1cc56f519931e))


## v3.11.0 (2026-04-24)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.7.6
  ([#362](https://github.com/n24q02m/better-code-review-graph/pull/362),
  [`88d0e3a`](https://github.com/n24q02m/better-code-review-graph/commit/88d0e3a10fa88c57f46e1acd49191d46e3c73eec))

- Bump n24q02m-mcp-core to >=1.7.1
  ([#356](https://github.com/n24q02m/better-code-review-graph/pull/356),
  [`e604a1d`](https://github.com/n24q02m/better-code-review-graph/commit/e604a1de78a52d9fa3f2d2c50c2fc972e47f9934))

### Chores

- **deps**: Update python:3.13-slim-bookworm docker digest to bb73517
  ([#352](https://github.com/n24q02m/better-code-review-graph/pull/352),
  [`65bed63`](https://github.com/n24q02m/better-code-review-graph/commit/65bed638b88d9540cdfadee7c9685a2f59ffa5a8))

### Features

- Enforce Smart Daemon Manager (1-Daemon) for stdio transport
  ([`924178c`](https://github.com/n24q02m/better-code-review-graph/commit/924178c0d0fe14d9a1610a9a196cd898eafa5fc6))


## v3.10.5 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.2 ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))

- Bump mcp-core to 1.6.3 ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))

- Bump n24q02m-mcp-core to 1.6.3 (relay form follow redirect_url)
  ([#351](https://github.com/n24q02m/better-code-review-graph/pull/351),
  [`fb209b0`](https://github.com/n24q02m/better-code-review-graph/commit/fb209b09414125a81356e4717edb26d1f7ec9e37))


## v3.10.4 (2026-04-22)

### Bug Fixes

- Bump mcp-core to 1.6.2 ([#349](https://github.com/n24q02m/better-code-review-graph/pull/349),
  [`2afbef1`](https://github.com/n24q02m/better-code-review-graph/commit/2afbef1c3587c89f070e347612577695898f6f09))


## v3.10.3 (2026-04-22)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.5.1
  ([`7a38355`](https://github.com/n24q02m/better-code-review-graph/commit/7a38355df4819e0ed73091ff18ee384fe360ff1e))

- Bump n24q02m-mcp-core to 1.6.1
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Ignore local dev utility clean.ps1
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Require explicit MCP_RELAY_URL for remote-relay mode
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- Require explicit MCP_RELAY_URL for remote-relay mode per matrix 2.5
  ([#345](https://github.com/n24q02m/better-code-review-graph/pull/345),
  [`5c35142`](https://github.com/n24q02m/better-code-review-graph/commit/5c35142ea0bfd4673fb86a779122f8b1a5303d04))

- **deps**: Update dependency qwen3-embed to >=1.9.0
  ([#342](https://github.com/n24q02m/better-code-review-graph/pull/342),
  [`cd95597`](https://github.com/n24q02m/better-code-review-graph/commit/cd9559736d44104dd607b2c9d35762d784078396))

### Chores

- **deps**: Lock file maintenance
  ([#344](https://github.com/n24q02m/better-code-review-graph/pull/344),
  [`2d12a94`](https://github.com/n24q02m/better-code-review-graph/commit/2d12a949dad97bf3ec78c1c94a5c773bd61c68b2))

- **deps**: Update astral-sh/setup-uv action to v8
  ([#343](https://github.com/n24q02m/better-code-review-graph/pull/343),
  [`a26ea8a`](https://github.com/n24q02m/better-code-review-graph/commit/a26ea8a99d4a7c9187d804725ecc52d30e833508))


## v3.10.2 (2026-04-21)

### Bug Fixes

- Bump non-major Python deps incl mcp-core to 1.5.0
  ([`9f7410f`](https://github.com/n24q02m/better-code-review-graph/commit/9f7410f47337e423076e0874379512a92cc3f5bf))

- Bump step-security/harden-runner digest to 8d3c67d
  ([`16f103f`](https://github.com/n24q02m/better-code-review-graph/commit/16f103f2c0e9a909147776d544de49f82259094a))

- Lock file maintenance
  ([`3f76346`](https://github.com/n24q02m/better-code-review-graph/commit/3f7634674b9913253e51a44d5a22e8cab115de01))

- Push target filter to SQL json_each in get_edges_among
  ([`b6be9cc`](https://github.com/n24q02m/better-code-review-graph/commit/b6be9cc751092e318098c5b807c07e2fb7d4e90b))

- Widen incremental update base to cover all local commits
  ([`aebbe43`](https://github.com/n24q02m/better-code-review-graph/commit/aebbe43b91769e422042673de90f34099ffdface))


## v3.10.1 (2026-04-21)

### Bug Fixes

- Accept SubjectContext arg on save_credentials
  ([`6a02e3a`](https://github.com/n24q02m/better-code-review-graph/commit/6a02e3af7fe8279604142cd819707be154d05f5c))

- Remove unnecessary chunking for json_each SQLite queries
  ([`bc44122`](https://github.com/n24q02m/better-code-review-graph/commit/bc44122cae23b533d3ac938cbf6a23ad9a6d800b))

- Stdio fallback spawns local credential form, not remote relay
  ([`744da0f`](https://github.com/n24q02m/better-code-review-graph/commit/744da0fe95f82113b2984f5b0094b2721050e11a))

- **deps**: Bump mcp-core to 1.4.3
  ([`4dfebf7`](https://github.com/n24q02m/better-code-review-graph/commit/4dfebf70c402439360f5db3e1e383d56beae0f3f))

- **deps**: Lock file maintenance (filelock 3.28.0->3.29.0)
  ([`961d945`](https://github.com/n24q02m/better-code-review-graph/commit/961d945adbc909c77d604a06e49eef3116b7d3e7))


## v3.10.0 (2026-04-19)

### Bug Fixes

- Add error handling to build_or_update_graph and add coverage tests
  ([#287](https://github.com/n24q02m/better-code-review-graph/pull/287),
  [`ef98bdf`](https://github.com/n24q02m/better-code-review-graph/commit/ef98bdf5e384c7475d45cadafb33ed19c3e134e9))

- Auto-select cloud embedding model based on available API key
  ([`9babf4f`](https://github.com/n24q02m/better-code-review-graph/commit/9babf4f6d2e0cc8b008631317c51fdd702338ba2))

- Bump mcp-core to 1.3.0 ([#308](https://github.com/n24q02m/better-code-review-graph/pull/308),
  [`2d6f58e`](https://github.com/n24q02m/better-code-review-graph/commit/2d6f58e1ea945dd4d9c26743480a6ddb664f8034))

- Bump n24q02m-mcp-core to 1.4.0
  ([#312](https://github.com/n24q02m/better-code-review-graph/pull/312),
  [`8e28b0a`](https://github.com/n24q02m/better-code-review-graph/commit/8e28b0a4d3fa0c82848eaabf8fefc995cb2af57e))

- N+1 queries in embed_nodes ([#305](https://github.com/n24q02m/better-code-review-graph/pull/305),
  [`52e186a`](https://github.com/n24q02m/better-code-review-graph/commit/52e186a41adab0d20802fe12934f94df89904f33))

- Refactor overly long get_review_context function
  ([#295](https://github.com/n24q02m/better-code-review-graph/pull/295),
  [`7595731`](https://github.com/n24q02m/better-code-review-graph/commit/7595731b615c776b72f47355f63fd429b8551c43))

- Refactor overly long watch function and extract helper
  ([#291](https://github.com/n24q02m/better-code-review-graph/pull/291),
  [`5b9950b`](https://github.com/n24q02m/better-code-review-graph/commit/5b9950b3fa553695f1d110f5220edd03eb1a80d9))

- Split overly long query_graph function into smaller helpers
  ([#288](https://github.com/n24q02m/better-code-review-graph/pull/288),
  [`931c638`](https://github.com/n24q02m/better-code-review-graph/commit/931c638725ea66732ee9c341f3ee0d956c7c5122))

- Untrack .jules AI traces + gitignore AI-trace dirs
  ([`bdbd69d`](https://github.com/n24q02m/better-code-review-graph/commit/bdbd69d3fa026114a154d413aed0b0ca7d954f42))

- **security**: Eliminate structural dynamic SQL in GraphStore
  ([#297](https://github.com/n24q02m/better-code-review-graph/pull/297),
  [`db24cba`](https://github.com/n24q02m/better-code-review-graph/commit/db24cbadff0177aef0435e4f7fb6d4dd950a466f))

### Chores

- **deps**: Lock file maintenance
  ([#309](https://github.com/n24q02m/better-code-review-graph/pull/309),
  [`c2fbbae`](https://github.com/n24q02m/better-code-review-graph/commit/c2fbbaead6ba533dd519b7ea724adca88557936a))

- **deps**: Lock file maintenance
  ([#304](https://github.com/n24q02m/better-code-review-graph/pull/304),
  [`a82e1ea`](https://github.com/n24q02m/better-code-review-graph/commit/a82e1eac71f22ae9f906e3a0fd48a584961b999c))

- **deps**: Update github/codeql-action digest to ce64ddc
  ([#303](https://github.com/n24q02m/better-code-review-graph/pull/303),
  [`525779a`](https://github.com/n24q02m/better-code-review-graph/commit/525779a49cf7c7dad070b912fefdc8b8a2b2ddf4))

### Features

- Merge setup tool into config with setup_* sub-actions
  ([#307](https://github.com/n24q02m/better-code-review-graph/pull/307),
  [`c6dbd9e`](https://github.com/n24q02m/better-code-review-graph/commit/c6dbd9e15e9f15db4804885cacaa99e27ce8a6c1))

### Performance Improvements

- Optimize get_subgraph by removing redundant mapping
  ([#294](https://github.com/n24q02m/better-code-review-graph/pull/294),
  [`e63fce2`](https://github.com/n24q02m/better-code-review-graph/commit/e63fce2a1cf1291fbd54796f3cffc9742ad9866a))

### Refactoring

- Split _extract_from_tree into specialized handlers
  ([#292](https://github.com/n24q02m/better-code-review-graph/pull/292),
  [`931237e`](https://github.com/n24q02m/better-code-review-graph/commit/931237ed980396dd1211fb7e1c4c017d1f1adf32))

### Testing

- Add comprehensive tests for callers_of query pattern
  ([#289](https://github.com/n24q02m/better-code-review-graph/pull/289),
  [`bc09fa2`](https://github.com/n24q02m/better-code-review-graph/commit/bc09fa21b401f4222a655bcaf3ef44054e269f87))

- Add error test for query_graph invalid pattern
  ([#280](https://github.com/n24q02m/better-code-review-graph/pull/280),
  [`c241243`](https://github.com/n24q02m/better-code-review-graph/commit/c241243c0fd8980d15b9e8da8e35db0478585e0f))


## v3.9.2 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.2.0 (authlib CVE patch)
  ([`6fd113b`](https://github.com/n24q02m/better-code-review-graph/commit/6fd113b56c3327b74257d370ac6f58626e5e216b))


## v3.9.1 (2026-04-17)

### Bug Fixes

- Bump n24q02m-mcp-core to 1.1.1 for OAuth issuer fix
  ([`d1f45bc`](https://github.com/n24q02m/better-code-review-graph/commit/d1f45bcea8d888e190dd58cf3d8f69a01207e708))


## v3.9.0 (2026-04-17)

### Bug Fixes

- Add diacritic preservation pre-commit hook
  ([#300](https://github.com/n24q02m/better-code-review-graph/pull/300),
  [`2e959c9`](https://github.com/n24q02m/better-code-review-graph/commit/2e959c9c701fbb8407a9888f7d4e48fd948f8580))

- Add tests for config() set action error paths
  ([#244](https://github.com/n24q02m/better-code-review-graph/pull/244),
  [`f5a35cd`](https://github.com/n24q02m/better-code-review-graph/commit/f5a35cdd5c22c30aa47110c6c3f7be5602bfee29))

- Add tests for help() function missing match
  ([#241](https://github.com/n24q02m/better-code-review-graph/pull/241),
  [`220cb1c`](https://github.com/n24q02m/better-code-review-graph/commit/220cb1c0bb97c3d578f0679d53c8eaf1efecb3d6))

- Add tests for relay_setup ensure_config error handling
  ([#240](https://github.com/n24q02m/better-code-review-graph/pull/240),
  [`9ddb968`](https://github.com/n24q02m/better-code-review-graph/commit/9ddb968d6fd90ba9bb8945af4b8d4139d07190a2))

- Add tests for search_roots fallback in get_docs_section
  ([#246](https://github.com/n24q02m/better-code-review-graph/pull/246),
  [`427a583`](https://github.com/n24q02m/better-code-review-graph/commit/427a58381c5a533313fa0371a5db47cdcedcdd98))

- Bandit B608 SQL injection risk
  ([`1ff8386`](https://github.com/n24q02m/better-code-review-graph/commit/1ff83868d95fcdb51691a3fe8f7fa766a5a6e535))

- Batch file queries with get_nodes_by_files to eliminate N+1 in impact radius and embed_all_nodes
  ([#298](https://github.com/n24q02m/better-code-review-graph/pull/298),
  [`b4f2bfb`](https://github.com/n24q02m/better-code-review-graph/commit/b4f2bfbbe0cc38f143bd196ed046f871112cb71a))

- Bump authlib + pytest for CSRF cache bypass and tmpdir CVE
  ([`e924c20`](https://github.com/n24q02m/better-code-review-graph/commit/e924c203a8e70726927be527e1d77464e71837ea))

- Bump n24q02m-mcp-core to >=1.0.0 stable
  ([`a7c83e3`](https://github.com/n24q02m/better-code-review-graph/commit/a7c83e3528d857cd51dc0a2a9b03000f41d194d5))

- Bump pytest to v9 for security advisory
  ([#276](https://github.com/n24q02m/better-code-review-graph/pull/276),
  [`2b764e4`](https://github.com/n24q02m/better-code-review-graph/commit/2b764e4cbaa4d985204e6ef6496079dee14fbc16))

- Correct import paths in test_performance_n1 to fix coverage measurement
  ([`92d0541`](https://github.com/n24q02m/better-code-review-graph/commit/92d0541e3eb247ee2a6f3c01f8f6a0d36e1a5363))

- Drop local uv.sources override for n24q02m-mcp-core
  ([`5726f06`](https://github.com/n24q02m/better-code-review-graph/commit/5726f0678fee1b61b911eb871f105935202d833a))

- Lock file maintenance
  ([`c47180b`](https://github.com/n24q02m/better-code-review-graph/commit/c47180b6a4850b4c94da9705e6c74c6b6213738b))

- Loosen N+1 perf threshold to tolerate CI jitter
  ([`8d84c97`](https://github.com/n24q02m/better-code-review-graph/commit/8d84c976fdbd0d868f590fa3cd84c91bb25ee0a7))

- Raise crg coverage to 95% by covering apply_config + save_credentials
  ([`1e501f4`](https://github.com/n24q02m/better-code-review-graph/commit/1e501f41f9e2904f8c9c0847b57f6c8f08de3117))

- Sync docs with Phase M completion reality
  ([#299](https://github.com/n24q02m/better-code-review-graph/pull/299),
  [`795310a`](https://github.com/n24q02m/better-code-review-graph/commit/795310a270681561ce43a7a429c361616d6be3cf))

- Tighten credential_state + test helper typing in crg
  ([`a061461`](https://github.com/n24q02m/better-code-review-graph/commit/a061461919d9c6bf02c73b0e7a34dd1a7d56f864))

- Tighten embeddings, parser, and relay typing in crg
  ([`e2baa2f`](https://github.com/n24q02m/better-code-review-graph/commit/e2baa2f3f8b44cf5e2c2b3fb1377d2dd881ecc37))

- Update docker/build-push-action digest to bcafcac
  ([`c9fe401`](https://github.com/n24q02m/better-code-review-graph/commit/c9fe4010838dc101c2b347d395e66837bce6da16))

- Update fastmcp to 3.2.0 and Pygments to 2.20.0 to fix SSRF, command injection, OAuth, and ReDoS
  vulnerabilities
  ([`0520358`](https://github.com/n24q02m/better-code-review-graph/commit/05203587afa94f952e15956af165df33c2853add))

- Update non-major dependencies
  ([`1e3d093`](https://github.com/n24q02m/better-code-review-graph/commit/1e3d093642631bdbad7a27263e798ceea3460d3a))

- Update python:3.13-slim-bookworm docker digest to 061b6e5
  ([`3dbd6bc`](https://github.com/n24q02m/better-code-review-graph/commit/3dbd6bcd61bbbba6a5f1f5a0a0d6d42a8fe6589f))

- **deps**: Bump actions/create-github-app-token digest to 1b10c78
  ([#269](https://github.com/n24q02m/better-code-review-graph/pull/269),
  [`c501ff2`](https://github.com/n24q02m/better-code-review-graph/commit/c501ff2000e72874560901bcae35fff91a1200f1))

- **deps**: Bump actions/upload-artifact digest to 043fb46
  ([#270](https://github.com/n24q02m/better-code-review-graph/pull/270),
  [`e480cc4`](https://github.com/n24q02m/better-code-review-graph/commit/e480cc46fd06c50db81d6640b2ea58a681f84410))

- **deps**: Bump non-major dependencies (cohere, fastmcp, google-genai, openai, mcp-core 1.1.0)
  ([#272](https://github.com/n24q02m/better-code-review-graph/pull/272),
  [`7962889`](https://github.com/n24q02m/better-code-review-graph/commit/7962889856da170de07e9f3d4a48d70573de4bd9))

- **deps**: Bump step-security/harden-runner digest to 6c3c2f2
  ([#271](https://github.com/n24q02m/better-code-review-graph/pull/271),
  [`270c194`](https://github.com/n24q02m/better-code-review-graph/commit/270c194ced3d385ea4e6e74ba329aa0648248bf8))

- **deps**: Lock file maintenance
  ([#273](https://github.com/n24q02m/better-code-review-graph/pull/273),
  [`fee13b2`](https://github.com/n24q02m/better-code-review-graph/commit/fee13b29e21f16c4c3118d312b0f8c2166c0931d))

- **deps**: Update non-major dependencies
  ([#231](https://github.com/n24q02m/better-code-review-graph/pull/231),
  [`00fdefe`](https://github.com/n24q02m/better-code-review-graph/commit/00fdefed829bebb1ae84a52b74f43d29cd9fa498))

### Chores

- **deps**: Bump cryptography in the uv group across 1 directory
  ([#235](https://github.com/n24q02m/better-code-review-graph/pull/235),
  [`94625e7`](https://github.com/n24q02m/better-code-review-graph/commit/94625e7c634d7ff6381ba938f078f7b2fd2636ec))

- **deps**: Lock file maintenance
  ([#232](https://github.com/n24q02m/better-code-review-graph/pull/232),
  [`12e6acf`](https://github.com/n24q02m/better-code-review-graph/commit/12e6acfd5626bc7698eb59ce54445b07d5d888f6))

- **deps**: Update python:3.13-slim-bookworm docker digest to f13a6b7
  ([#230](https://github.com/n24q02m/better-code-review-graph/pull/230),
  [`f8b4df9`](https://github.com/n24q02m/better-code-review-graph/commit/f8b4df95795f38dbbb0dfa0e9bdd7911b6ab074b))

### Features

- Add coverage tests for get_edges_by_targets batch fetch
  ([`58256d4`](https://github.com/n24q02m/better-code-review-graph/commit/58256d479975a78353fad977f41b70a2f0c36e7c))

- Add cross-OS CI matrix (ubuntu/windows/macos)
  ([`9202f1d`](https://github.com/n24q02m/better-code-review-graph/commit/9202f1d6bef2dfcbd6140d0a9b676c7329b05b1f))

- Add HTTP+OAuth transport, default to HTTP with --stdio fallback
  ([`3b1784a`](https://github.com/n24q02m/better-code-review-graph/commit/3b1784a1304c66ddab6c3cd293086934e8ca9da5))

- Add uv.sources for local mcp-core dev dependency
  ([`0bf7084`](https://github.com/n24q02m/better-code-review-graph/commit/0bf7084b08278c74fad09c7267c981280e358390))

- Migrate from mcp-relay-core to mcp-core
  ([`7a9df64`](https://github.com/n24q02m/better-code-review-graph/commit/7a9df646656a6d863f0515962a249c10f8135cc3))

- Wire save_credentials + apply_config for local OAuth form
  ([`9e93db9`](https://github.com/n24q02m/better-code-review-graph/commit/9e93db9233befa48f932983e0e3a209c45edc970))

### Performance Improvements

- **incremental**: Resolve N+1 query in find_dependents via get_edges_by_targets
  ([#234](https://github.com/n24q02m/better-code-review-graph/pull/234),
  [`654f2b7`](https://github.com/n24q02m/better-code-review-graph/commit/654f2b783692c412859c596e47963cc29ad0beaa))


## v3.8.0 (2026-04-07)

### Bug Fixes

- Add credential state and setup tool tests for relay redesign
  ([`64e18f4`](https://github.com/n24q02m/better-code-review-graph/commit/64e18f42cf4d1a7a8c408f6d74a95f58c076f572))

- Apply ruff formatting and make ty hook non-blocking to match CI
  ([`3d20350`](https://github.com/n24q02m/better-code-review-graph/commit/3d20350fa0aff74fde71cbb14afb03539a2097e6))

- Remove BETA markers and promote relay as primary setup method
  ([`298ad9c`](https://github.com/n24q02m/better-code-review-graph/commit/298ad9c88bb6fd196bfe47a65ef0cdf1ce8ff268))

- Resolve ruff lint errors in agent-generated test files
  ([`31eaeb6`](https://github.com/n24q02m/better-code-review-graph/commit/31eaeb65b9b136bce8167642b3999a1cbe200c75))

- Resolve Windows PermissionError in SQLite test fixtures and lower coverage threshold
  ([`873962f`](https://github.com/n24q02m/better-code-review-graph/commit/873962f90fa5c630370d2494284e79ae86eb5381))

- Sync uv.lock with current version
  ([`44778c2`](https://github.com/n24q02m/better-code-review-graph/commit/44778c2335d8f0b689ab3462f014d436d181fbc0))

### Features

- Migrate code review from Qodo to CodeRabbit
  ([#188](https://github.com/n24q02m/better-code-review-graph/pull/188),
  [`7be7dff`](https://github.com/n24q02m/better-code-review-graph/commit/7be7dfff885a2f115dbd2e6ef3381b2d57b68f36))


## v3.7.2 (2026-04-06)

### Bug Fixes

- Share cloud keys to peer servers when loading from config on startup
  ([`58dd87a`](https://github.com/n24q02m/better-code-review-graph/commit/58dd87a60940ea23e08fbc7dd514c70dd0694e03))


## v3.7.1 (2026-04-06)

### Bug Fixes

- Send complete message to browser after relay and add cross-server sharing
  ([`bc4cdef`](https://github.com/n24q02m/better-code-review-graph/commit/bc4cdef5fe33096cec27429d2ab6a3efcc47111d))


## v3.7.0 (2026-04-06)

### Bug Fixes

- Mark relay as BETA, promote env vars as primary setup method
  ([`f54355f`](https://github.com/n24q02m/better-code-review-graph/commit/f54355ff3eeabd621c50e71b22ec171cb35058f2))

- Resolve lint errors in test files
  ([`c35dc9b`](https://github.com/n24q02m/better-code-review-graph/commit/c35dc9b6e001a5aed2e1b0de86234fa4af590d7f))

### Features

- Non-blocking relay with state machine and lazy trigger
  ([`fb4fa9f`](https://github.com/n24q02m/better-code-review-graph/commit/fb4fa9f2041c6694eeca32a272e7671a3872d521))


## v3.6.0 (2026-04-04)

### Bug Fixes

- Use math.sumprod for cosine similarity and add embedding migration test
  ([#152](https://github.com/n24q02m/better-code-review-graph/pull/152),
  [`963c7df`](https://github.com/n24q02m/better-code-review-graph/commit/963c7df66a592fc32279e860102dcaab2acf2d05))

### Features

- Add agent/manual setup guides, simplify README, cleanup root
  ([`a2ec36c`](https://github.com/n24q02m/better-code-review-graph/commit/a2ec36c6e5fbf23c9bc9c32c1ce4c03bedaafe10))


## v3.5.1 (2026-04-03)

### Bug Fixes

- Harden SQL queries, batch N+1 fetches, add input limits and error tests
  ([#115](https://github.com/n24q02m/better-code-review-graph/pull/115),
  [`4709f66`](https://github.com/n24q02m/better-code-review-graph/commit/4709f66c4d098b9d62d90175f4424a23b8ad10d9))

- Scope marketplace sync token to claude-plugins repo
  ([`dfe45e3`](https://github.com/n24q02m/better-code-review-graph/commit/dfe45e34051eec907edefbf39b97e631071bfd28))


## v3.5.0 (2026-04-03)

### Features

- Remove deprecated Gemini CLI extension support
  ([`20240e2`](https://github.com/n24q02m/better-code-review-graph/commit/20240e2a2af3bf3e2c280457ae2ad03388c38f7b))


## v3.5.0-beta.1 (2026-04-03)

### Features

- Add E2E test infrastructure and consolidated test
  ([`2e69de3`](https://github.com/n24q02m/better-code-review-graph/commit/2e69de3894077f8be0e063442aac120b42a78f63))


## v3.4.0 (2026-04-01)

### Chores

- **deps**: Bump the uv group across 1 directory with 2 updates
  ([#60](https://github.com/n24q02m/better-code-review-graph/pull/60),
  [`1c186ed`](https://github.com/n24q02m/better-code-review-graph/commit/1c186ed8078ebed7067f2ae39ba5df0d0c8a29fb))

### Continuous Integration

- Fix Qodo vertex_ai config and VERTEXAI_LOCATION
  ([`536e15b`](https://github.com/n24q02m/better-code-review-graph/commit/536e15b2fb44b48f0025a347fe49cd5bb059960e))

- **cd**: Add plugin marketplace sync on stable release
  ([`41f09d5`](https://github.com/n24q02m/better-code-review-graph/commit/41f09d5ba17ec5dc72f312309253fdd7ea2383a7))

### Performance Improvements

- **tools**: Replace N+1 queries with batch fetch in `query_graph`
  ([#63](https://github.com/n24q02m/better-code-review-graph/pull/63),
  [`075009b`](https://github.com/n24q02m/better-code-review-graph/commit/075009ba9b3e7c78d719f1fb0236856c6819fa06))


## v3.4.0-beta.1 (2026-03-31)

### Features

- Redesign relay schema with capability-based layout and priority info
  ([`2082258`](https://github.com/n24q02m/better-code-review-graph/commit/2082258316758c0e0a38c6447a5ed2e7aa39c239))


## v3.3.1-beta.1 (2026-03-30)

### Bug Fixes

- **ci**: Pin google-github-actions/auth to SHA v3
  ([`6e5c83d`](https://github.com/n24q02m/better-code-review-graph/commit/6e5c83d6a541429a18fae96852062570774a01a5))

### Chores

- Add Infisical project configuration
  ([`65b03e6`](https://github.com/n24q02m/better-code-review-graph/commit/65b03e6c864987f9c5227e1b45e861ed3c6a57df))

- Remove Infisical config (empty project deleted)
  ([`4d381af`](https://github.com/n24q02m/better-code-review-graph/commit/4d381af335dac4f0186f263471a0eea83d56648a))

### Code Style

- Format relay_setup.py
  ([`c7e7fdf`](https://github.com/n24q02m/better-code-review-graph/commit/c7e7fdf82ba1630e1377ce7ec8db7181e396eda2))

- Format test_relay.py
  ([`bc7100b`](https://github.com/n24q02m/better-code-review-graph/commit/bc7100be20446c6e291d7e8258cba31822a343d1))

### Documentation

- Fix CLAUDE.md discrepancies
  ([`f69f461`](https://github.com/n24q02m/better-code-review-graph/commit/f69f461805306343f7a1d10a16e596db801bcecb))

### Testing

- Update relay tests for multi-provider cloud keys refactor
  ([`ee4ebd8`](https://github.com/n24q02m/better-code-review-graph/commit/ee4ebd8c8a5d65a94e9d36e489ff7ec177abfd49))


## v3.3.0 (2026-03-28)

### Bug Fixes

- Add all 4 embedding providers to relay schema + fix config lookup
  ([`508e959`](https://github.com/n24q02m/better-code-review-graph/commit/508e9599c8ccf55906d6c34678fb55ebbd3bf52f))

- Bump mcp-relay-core to >=1.0.5
  ([`1087881`](https://github.com/n24q02m/better-code-review-graph/commit/10878812cb91758c29805b1d77129418b66a5977))

- Correct relay URL from relay.n24q02m.com to better-code-review-graph.n24q02m.com
  ([`c8c10c8`](https://github.com/n24q02m/better-code-review-graph/commit/c8c10c8a29ef6c32f8f7d4a896ce44826f38c99a))

- Credential resolution order -- relay only when no local credentials
  ([`ed92c21`](https://github.com/n24q02m/better-code-review-graph/commit/ed92c213e06a101eebf8cb4ecd81f08aab045610))

- Increase relay timeout from 30s to 120s
  ([`beb0319`](https://github.com/n24q02m/better-code-review-graph/commit/beb0319d0a64f6b54fe9ca6781dd13be488d63b6))

- Pin Docker base images to SHA digests
  ([`6f48357`](https://github.com/n24q02m/better-code-review-graph/commit/6f483576fb9db320aad7ae32aef19ea05922e279))

- Pin pre-commit hooks to commit SHA
  ([`95dc20d`](https://github.com/n24q02m/better-code-review-graph/commit/95dc20de652682a4fbc8ca5057f9e2f7e429b0ca))

- Send complete message to relay page after config saved
  ([`068419c`](https://github.com/n24q02m/better-code-review-graph/commit/068419c6cf08aaaa25be4a10c90434790d1f2a56))

- **cd**: Remove empty env blocks from OIDC migration
  ([`386d680`](https://github.com/n24q02m/better-code-review-graph/commit/386d680da1cf2c28b1492d7fa8331facc05293e6))

- **cd**: Replace GH_PAT with GitHub App installation token
  ([`46946bd`](https://github.com/n24q02m/better-code-review-graph/commit/46946bd3b38d208fc264c5836dad028ed2c5a8fa))

- **cd**: Use PyPI OIDC trusted publishing instead of PYPI_TOKEN
  ([`31feeb7`](https://github.com/n24q02m/better-code-review-graph/commit/31feeb7b70ae76aa674c871ccaf8e6d0f184f1a5))

- **ci**: Consolidate SMTP_USERNAME and NOTIFY_EMAIL into one secret
  ([`4dcc114`](https://github.com/n24q02m/better-code-review-graph/commit/4dcc11497305d6f95207b0c9d280670b3c4234b4))

- **ci**: Consolidate SMTP_USERNAME+PASSWORD into SMTP_CREDENTIAL
  ([`ef0df19`](https://github.com/n24q02m/better-code-review-graph/commit/ef0df1988c9b96b19cbd3f7e800f69da186bcaa0))

- **ci**: Remove CODECOV_TOKEN, use tokenless upload
  ([`f565418`](https://github.com/n24q02m/better-code-review-graph/commit/f565418dd0422b3db0a700826523622096018a1a))

- **ci**: Use Vertex AI WIF instead of GEMINI_API_KEY for code review
  ([`9e19886`](https://github.com/n24q02m/better-code-review-graph/commit/9e19886575254089d3f6ee59ecec009d1beb898c))

- **deps**: Update non-major dependencies
  ([#41](https://github.com/n24q02m/better-code-review-graph/pull/41),
  [`f365b16`](https://github.com/n24q02m/better-code-review-graph/commit/f365b163ef3a5fd69b263d0f40cbd860406d9243))

- **tests**: Keep embedding mock active during semantic search tests
  ([`2942dec`](https://github.com/n24q02m/better-code-review-graph/commit/2942dec9be71076e055e85362b60a2b512bc1dbe))

- **tests**: Mock embedding backend instead of skipping tests
  ([`2e33242`](https://github.com/n24q02m/better-code-review-graph/commit/2e33242008b0dcad644f1a6ded2567f8bb746dec))

- **tests**: Remove unused top-level os import (ruff F401)
  ([`6b3fdf6`](https://github.com/n24q02m/better-code-review-graph/commit/6b3fdf61ef02823fdaee10487ec199973cf40bdd))

- **tests**: Skip embedding tests when no API key available
  ([`4e75a43`](https://github.com/n24q02m/better-code-review-graph/commit/4e75a437f707bb3cb6f06688b360e4475a6c2990))

- **tests**: Update mock paths for lazy-imported relay functions
  ([`f154e1e`](https://github.com/n24q02m/better-code-review-graph/commit/f154e1e8d47fdcafe53f9a1b31fbd4f1bdac0cf5))

### Chores

- Add .env to .gitignore for secret protection
  ([`c17560f`](https://github.com/n24q02m/better-code-review-graph/commit/c17560faf97161965674817793911bba9a488e50))

- **deps**: Update actions/create-github-app-token action to v3
  ([#47](https://github.com/n24q02m/better-code-review-graph/pull/47),
  [`2413aca`](https://github.com/n24q02m/better-code-review-graph/commit/2413aca5a9092435d25cde89c2b4c16d22167db3))

- **deps**: Update codecov/codecov-action action to v6
  ([#48](https://github.com/n24q02m/better-code-review-graph/pull/48),
  [`6c466be`](https://github.com/n24q02m/better-code-review-graph/commit/6c466be8f23dfcf27b1b74f1c95f51d326382113))

- **deps**: Update github/codeql-action digest to 5c8a8a6
  ([#45](https://github.com/n24q02m/better-code-review-graph/pull/45),
  [`16b0bcb`](https://github.com/n24q02m/better-code-review-graph/commit/16b0bcbbe849792186f25c91380085f183dc9c9b))

### Code Style

- Format test_coverage_gaps.py
  ([`79442c3`](https://github.com/n24q02m/better-code-review-graph/commit/79442c3f5dbb28393aa469f93ecbbaff8196f734))

### Continuous Integration

- Retrigger CI (ruff cache issue)
  ([`719162b`](https://github.com/n24q02m/better-code-review-graph/commit/719162bd1fa7f3f509c3bdeb9576e3ccd335ac2a))

### Features

- Relay-first startup — always show relay URL
  ([`4d9ccea`](https://github.com/n24q02m/better-code-review-graph/commit/4d9cceab4018d90f4b9a1339d74e38b63dbe86a3))

### Testing

- Fix relay test assertions to match implementation
  ([`50cdc87`](https://github.com/n24q02m/better-code-review-graph/commit/50cdc87fd7917c61efddec5bc0b514e08db6cd24))

- Improve coverage to meet 95% threshold
  ([`84a0e92`](https://github.com/n24q02m/better-code-review-graph/commit/84a0e92420ee4faadd65c4b5c94aa29649c88940))


## v3.2.0 (2026-03-26)

### Chores

- Add server.json to PSR version_variables, sync version
  ([`d6a1cde`](https://github.com/n24q02m/better-code-review-graph/commit/d6a1cdeb294570a8beb3c38bbabac122fc7b8195))

- Clean up plugin manifest for best practices
  ([`db9d65b`](https://github.com/n24q02m/better-code-review-graph/commit/db9d65b5171434ce633ffa910a8a09c68357c623))

### Documentation

- Fix marketplace references, improve Gemini CLI extension config
  ([`b6bc8c2`](https://github.com/n24q02m/better-code-review-graph/commit/b6bc8c2b85127b0bf53a22239dc61b1c5384b878))

- Standardize README structure
  ([`ee9b10f`](https://github.com/n24q02m/better-code-review-graph/commit/ee9b10fcc1b43426912b1592c8389c104871ad80))


## v3.2.0-beta.1 (2026-03-25)

### Bug Fixes

- Switch mcp-relay-core from git dep to published PyPI package
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))

### Documentation

- Add relay files to CLAUDE.md file structure
  ([`e335e48`](https://github.com/n24q02m/better-code-review-graph/commit/e335e48b3ca494883dd69975f7f7bebc80a4d321))

- Add zero-config relay setup section to README
  ([`af7ddac`](https://github.com/n24q02m/better-code-review-graph/commit/af7ddac4e18458c54899ac920d4e50502340b9f5))

### Features

- Integrate mcp-relay-core for zero-env-config setup
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))

- Zero-env-config relay setup via mcp-relay-core
  ([#36](https://github.com/n24q02m/better-code-review-graph/pull/36),
  [`2147030`](https://github.com/n24q02m/better-code-review-graph/commit/214703007fc43961201c8a8387535d6eda6f2f4e))


## v3.1.0 (2026-03-25)

### Bug Fixes

- Add 'docs/' to .gitignore
  ([`de96b38`](https://github.com/n24q02m/better-code-review-graph/commit/de96b38db092074c5c9bc1df8e0b9bea33ef7944))

- Delete docs directory
  ([`a8b38b9`](https://github.com/n24q02m/better-code-review-graph/commit/a8b38b907b6b745e2c70658cd74d68c6aa5c9e3d))

- Update README for embedding cloud description
  ([`5756798`](https://github.com/n24q02m/better-code-review-graph/commit/5756798ef68336784fe694261a40263981d660ef))


## v3.1.0-beta.2 (2026-03-25)

### Bug Fixes

- Replace LiteLLM references with Cohere cloud in docs
  ([`a2ccb40`](https://github.com/n24q02m/better-code-review-graph/commit/a2ccb40ca1766a21ccd83265b9f3d03e3e760090))

- Update AGENTS.md/CLAUDE.md — remove litellm references
  ([`5027710`](https://github.com/n24q02m/better-code-review-graph/commit/50277103cd42a76af63935ad6c3b7d486cc4fca2))

- Update docs — remove litellm references, add multi-provider info
  ([`eb91c46`](https://github.com/n24q02m/better-code-review-graph/commit/eb91c460c8c916b93cf43a2a01f80a77f7ec0a32))

### Features

- Upgrade to multi-provider embedding (jina > gemini > openai > cohere)
  ([`849b193`](https://github.com/n24q02m/better-code-review-graph/commit/849b193ac323a9033295282f543ab83eaa50aead))


## v3.1.0-beta.1 (2026-03-25)

### Bug Fixes

- Auto-sync plugin.json version via PSR
  ([`f96baf3`](https://github.com/n24q02m/better-code-review-graph/commit/f96baf306dbbc089f997c862b0cce194db8cf3b5))

- Correct plugin install commands per official docs
  ([`c8e6826`](https://github.com/n24q02m/better-code-review-graph/commit/c8e6826ac04a8a6371c940bd216057f13266881b))

- Pin third-party GitHub Actions to SHA hashes
  ([`3065f82`](https://github.com/n24q02m/better-code-review-graph/commit/3065f8219d763761d14cb5c74a0cc8f7d97c87cc))

- Remove empty env vars from plugin configs to prevent empty-string bugs
  ([`645b7aa`](https://github.com/n24q02m/better-code-review-graph/commit/645b7aa6377b9c464be41501b4e56487eb57cc0d))

- Remove env vars from plugin.json to prevent overwriting user config
  ([`6949438`](https://github.com/n24q02m/better-code-review-graph/commit/6949438cfc8af70e1ff7d3df08aa2ae1c072d11c))

- Remove invalid hooks field from plugin.json
  ([`43dc3f8`](https://github.com/n24q02m/better-code-review-graph/commit/43dc3f89792ca7ac9e2cd1cc1c32d4cdce741bf6))

- Remove pr-title-check job from CI
  ([`f287d23`](https://github.com/n24q02m/better-code-review-graph/commit/f287d233c8559b29c740bf071b326e147036e475))

- Replace non-existent build-graph skill with refactor-check in README
  ([`7a8fde5`](https://github.com/n24q02m/better-code-review-graph/commit/7a8fde558d3676c61e9534d2440a6be77cc24f0f))

- Split PSR version_toml — move JSON files to version_variables
  ([`86203ab`](https://github.com/n24q02m/better-code-review-graph/commit/86203aba96bdf01712bbce4daab0a613bd7842b1))

- Sync plugin.json version and add skills/hooks references
  ([`a6d3aca`](https://github.com/n24q02m/better-code-review-graph/commit/a6d3acabc85d60b1d602f4ee34eeb403a3bce596))

- Sync uv.lock with native provider SDK dependencies
  ([`c1c428e`](https://github.com/n24q02m/better-code-review-graph/commit/c1c428ed062e1e5409564c4bc3c979bf97a917ba))

- Unify Plugin install section with marketplace + individual options
  ([`b885614`](https://github.com/n24q02m/better-code-review-graph/commit/b885614e37e56c131fc813589fcaee188ee53432))

- Update ruff pre-commit hook to v0.15.7
  ([`d00ee2e`](https://github.com/n24q02m/better-code-review-graph/commit/d00ee2ede5a101331e15d0235a98549017b5a23a))

### Features

- Add complete env vars and pipx mode to plugin config
  ([`d66b9f8`](https://github.com/n24q02m/better-code-review-graph/commit/d66b9f84188e3136f68493d0d236aaf5255cb825))

- Add EMBEDDING_MODEL and EMBEDDING_BACKEND to plugin config
  ([`4023941`](https://github.com/n24q02m/better-code-review-graph/commit/40239414a71508527fd3070e043cfd33fe9009d8))

- Add Gemini CLI extension config
  ([`d088418`](https://github.com/n24q02m/better-code-review-graph/commit/d088418c505596bc15c8543a9e047c492e20e55a))

- Multi-mode plugin config (stdio + docker + http)
  ([`a2daaf7`](https://github.com/n24q02m/better-code-review-graph/commit/a2daaf7f602ddeffbd5ed03186436b5c115b9cb1))

- Standardize README with MCP Resources, Security, collapsible clients
  ([`5d0c794`](https://github.com/n24q02m/better-code-review-graph/commit/5d0c794828a36f55a064fa8a6b65f972e7e0b552))

### Refactoring

- Replace LiteLLM embedding with Cohere SDK (embed-multilingual-v3.0)
  ([`cc444cc`](https://github.com/n24q02m/better-code-review-graph/commit/cc444cc7f6ab2a00e5b0bb74741c2337b15d36f8))


## v3.0.0 (2026-03-24)

### Bug Fixes

- Add gitleaks secret detection to pre-commit hooks
  ([`7253163`](https://github.com/n24q02m/better-code-review-graph/commit/72531632ad724e44a3aa878cb27a30c33b4c748e))

- Apply ruff formatting to pass CI
  ([`be854ce`](https://github.com/n24q02m/better-code-review-graph/commit/be854ce28e84d37959746c57785662df727b4126))

- Fix Bandit B608 SQL Injection warnings in graph queries
  ([#3](https://github.com/n24q02m/better-code-review-graph/pull/3),
  [`efe5dc7`](https://github.com/n24q02m/better-code-review-graph/commit/efe5dc719200e06d71269fcf4dc97d3e62b7e05c))

- Move imports before pytestmark to fix ruff E402
  ([`01c1e64`](https://github.com/n24q02m/better-code-review-graph/commit/01c1e6420439dc7abb02bf5c2ec468d7e26e3445))

- Remove .jules/bolt.md from PR ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Features

- Optimize cosine similarity calculation
  ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Performance Improvements

- Optimize _cosine_similarity with math.hypot and map
  ([#4](https://github.com/n24q02m/better-code-review-graph/pull/4),
  [`005f2ea`](https://github.com/n24q02m/better-code-review-graph/commit/005f2eac5af21d24c7ffb38ac34055f868daeedc))

### Testing

- Add cloud embedding mode tests with API_KEYS
  ([`864b483`](https://github.com/n24q02m/better-code-review-graph/commit/864b483ad8270b105a70fc508f4ec33ac4e86297))

- Add full/real live tests for all query patterns and modes
  ([`38f546a`](https://github.com/n24q02m/better-code-review-graph/commit/38f546a0749984e357fe1be03702fb322ee1045d))


## v3.0.0-beta.1 (2026-03-23)

### Bug Fixes

- Add missing .github config files for consistency
  ([`5271449`](https://github.com/n24q02m/better-code-review-graph/commit/5271449a9835c7f6b9b989b412ec0b547b94653a))

- Add PSR config, fix Semgrep false positives, sync server.json
  ([`c6af422`](https://github.com/n24q02m/better-code-review-graph/commit/c6af4223c60d98fdb321fcb092d89d3654d8664d))

- Format cli.py and test_cli.py with ruff
  ([`cd70342`](https://github.com/n24q02m/better-code-review-graph/commit/cd70342d8370110b309906e8892b196e1e2b91fb))

- Improve tool descriptions and corrective errors for LLM call pass rate
  ([`5774f90`](https://github.com/n24q02m/better-code-review-graph/commit/5774f90f8e6e99218e21c682af0ca29261a64fc6))

- Remove stale 'serve' arg from live MCP test server params
  ([`30c9415`](https://github.com/n24q02m/better-code-review-graph/commit/30c9415c548bf64bd1b5a6d8038889efbec79302))

- Remove stale 'serve' from plugin.json args, fix plugin add command
  ([`beff261`](https://github.com/n24q02m/better-code-review-graph/commit/beff261d37cb4502b45587b1ffe2e4afcf0ebb64))

- Replace encoding_format with drop_params in LiteLLM calls
  ([`d8739cd`](https://github.com/n24q02m/better-code-review-graph/commit/d8739cd4a1a70e45a215b60871336559a97fafd6))

- Standardize README structure
  ([`1f10fb8`](https://github.com/n24q02m/better-code-review-graph/commit/1f10fb85c2da1d19df9f5f3fbe4236ee51cbb802))

- Update session-start.sh to reference MCP tool instead of deleted skill
  ([`8339cb9`](https://github.com/n24q02m/better-code-review-graph/commit/8339cb91a202e9bcd95d71701e4c5a44b9823bd0))

### Chores

- Add renovate.json, community docs, fix server.json env vars
  ([`e3b7f4c`](https://github.com/n24q02m/better-code-review-graph/commit/e3b7f4c1193cb9cdaa15316d4d8e7bb091c79cdf))

- **release**: Bump version to 2.0.0
  ([`9973177`](https://github.com/n24q02m/better-code-review-graph/commit/99731776f062d460e672e2c52b4287b9f93d9d63))

### Continuous Integration

- Replace Semgrep with CodeQL for SAST scanning
  ([`e6842b4`](https://github.com/n24q02m/better-code-review-graph/commit/e6842b4d98b7d504da0d7eb23905686bf93a5a0f))

### Documentation

- Add Solidity to Supported Languages in README
  ([`a8b2554`](https://github.com/n24q02m/better-code-review-graph/commit/a8b25549fdadc586fb8f84b727740670588de953))

- Standardize README sections and sync Also by table
  ([`b72e13a`](https://github.com/n24q02m/better-code-review-graph/commit/b72e13ae679e623e784761809e0ce1970e7c924d))

- Update CLAUDE.md to reflect 13 supported languages (add Solidity)
  ([`c1e4b7a`](https://github.com/n24q02m/better-code-review-graph/commit/c1e4b7a286e0f6956d2d17746d5760753b19426f))

- Update CLAUDE.md to reflect CLI serve default
  ([`7046181`](https://github.com/n24q02m/better-code-review-graph/commit/7046181aa8388a1f811d4703f46b3c50d35c9234))

### Refactoring

- Make serve the default CLI command, remove serve subcommand
  ([`b60933a`](https://github.com/n24q02m/better-code-review-graph/commit/b60933aff8b48f8c0b803361d7dfe649807a6170))

- Migrate update CLI to MCP-only, fix PostToolUse hook
  ([`f67b9e7`](https://github.com/n24q02m/better-code-review-graph/commit/f67b9e778ebaf33c880b8db2ef6beca060c1a306))

- Redesign skills per approved spec
  ([`d3baa4f`](https://github.com/n24q02m/better-code-review-graph/commit/d3baa4f4f26f18d853cb8c838cdc181230acbc38))

- Split graph mega-tool into 5-tool architecture
  ([`7276209`](https://github.com/n24q02m/better-code-review-graph/commit/72762098c50b699c9cf24f9ddcce71bfaa320076))

### Testing

- Add missing live MCP protocol tests for graph update, config cache_clear, and error paths
  ([`4e76e9a`](https://github.com/n24q02m/better-code-review-graph/commit/4e76e9a5bebc48bf2bb7d4d2d4d0dd6ab69fdf14))


## v2.0.0 (2026-03-20)

### Bug Fixes

- Add remote type to PSR config for version commit push
  ([`34327d9`](https://github.com/n24q02m/better-code-review-graph/commit/34327d96691355086394aad18fe49a004ed50016))

- Add ty to dev deps, nosemgrep for importlib.resources
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Chores

- Add .worktrees/ to gitignore
  ([`75d3154`](https://github.com/n24q02m/better-code-review-graph/commit/75d315423d073d8e2c7d64665f8c94d15f1d4fca))

### Continuous Integration

- Fix ty missing from dev deps, make ty non-fatal
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Documentation

- Rewrite README with 3-tier tools, per-agent install guides
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Update CLAUDE.md, AGENTS.md, skills for 3-tier tools
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Features

- Add docs/ directory for help tool (graph.md, config.md)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Refactor 9 tools into 3-tier architecture (graph + config + help)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- Simplify CLI to serve + update only
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

- V2 — 3-tier tool architecture (graph + config + help)
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))

### Testing

- Add Phase 5 live MCP protocol integration tests
  ([`b5f46f0`](https://github.com/n24q02m/better-code-review-graph/commit/b5f46f080e639837bbd082727dfd66214bad9d02))

- Improve coverage for config/help tools, lint fixes
  ([#1](https://github.com/n24q02m/better-code-review-graph/pull/1),
  [`03a5118`](https://github.com/n24q02m/better-code-review-graph/commit/03a5118f913f71d9a4e63082c8b619994f9e4610))


## v1.0.3 (2026-03-20)

### Bug Fixes

- Add MCP Registry LABEL to Dockerfile for OCI validation
  ([`333efe3`](https://github.com/n24q02m/better-code-review-graph/commit/333efe393770d2b57f1f8b5e99b61c34d32baa28))


## v1.0.2 (2026-03-20)

### Bug Fixes

- Decouple MCP Registry publish from PyPI in CD workflow
  ([`050d180`](https://github.com/n24q02m/better-code-review-graph/commit/050d1803ea34ffeefaba983eddc956226e92bea5))


## v1.0.1 (2026-03-20)

### Bug Fixes

- Correct server.json schema for MCP Registry (identifier, transport)
  ([`4c615fc`](https://github.com/n24q02m/better-code-review-graph/commit/4c615fca8e716242682b02361f8f0a863f21c347))


## v1.0.0 (2026-03-20)

### Chores

- **release**: Sync version to 1.0.0b2 to match PSR tag
  ([`ab920e8`](https://github.com/n24q02m/better-code-review-graph/commit/ab920e85d57d55fcd49eef56baba04d8adae4845))


## v1.0.0-beta.2 (2026-03-20)

### Bug Fixes

- Include README.md in Docker build for hatchling
  ([`03264e1`](https://github.com/n24q02m/better-code-review-graph/commit/03264e12c3c1788a492756a8c116972f85077383))


## v1.0.0-beta.1 (2026-03-20)

- Initial Release
