# Configuration templates and local instances

[简体中文](CONFIGURATION.md)

`instance-settings.json` is a standard JSON template. JSON has no comments, so its `_comment` array contains explanatory text. `selected: null` and `instances: {}` mean that a fresh clone has no runnable instance. `templates` provides starting points for four locally tested versions; templates are never selected automatically.

| Placeholder | Required value |
|---|---|
| `${JAVA_BIN}` | Java executable compatible with this game version |
| `${CLIENT_DIRECTORY}` | Matching installed client directory |
| `${LIBRARIES_ROOT}` | Directory containing libraries and assets |
| `${SERVER_DIRECTORY}` | Managed copy or external server directory |

Prefer `./setup.sh` option 6 for vanilla installation, or `./setup.sh --server-dir /srv/minecraft` for an existing server. The wizard writes resolved profiles only to ignored `local-instances.json`, leaving public templates unchanged.

For manual configuration, use `{"instances":{"my-world":{...filled template...}}}` and run `python3 scripts/instances.py select my-world` after preparing the environment/resources. Every placeholder must be resolved. Errors identify unfilled values and point to setup.sh. Relative paths resolve against the workspace; select it with `MCBENCH_WORKSPACE` or `mcbench --workspace /path/to/checkout`.

Selection precedence: `MC_INSTANCE`, then `runtime/selected-instance.json`, then the public selected field (empty by default). Local profiles override public profiles of the same name. `MINECRAFT_JAVA_BIN` overrides an instance's Java path; the generic fallback searches PATH. llama.cpp defaults to workspace engines/llama.cpp. Custom machine paths belong in local-settings.json.

New worlds need distinct instance IDs, world_id values and memory directories. Upgrades retain existing player names, world IDs and server locations. Existing built-in local profiles were copied to private configuration before this migration. If prompt.md is absent, legacy agent_prompt.md is copied without deleting the old file.

Connection-only mode uses server.managed=false, requires no server.jar field, leaves the original server running and applies no test rules. Copy mode requires stopping the source first.
