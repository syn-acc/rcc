# Compute providers

Store named profiles in `/etc/rcc/providers.json`, or point `--config FILE` or `RCC_CONFIG` at an operator-owned file. The default Colab profile already talks to RUUF’s broker on `/run/ruu-legs.sock`. Its credentials, spending rules and scorer stay with RUUF. [Colab broker](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/legs/runner.py)

## Connect a home workstation

Create a Docker context for the machine, for example `docker context create home --docker host=ssh://operator@workstation`. Preload your worker image on that engine. The image needs GNU `/usr/bin/timeout` and an entrypoint that reads the experiment JSON from `RCC_PARAMS_JSON`. Use the actual image digest reported by Docker. [Docker over SSH](https://docs.docker.com/engine/security/protect-access/)

```json
{
  "providers": {
    "home": {
      "driver": "docker",
      "config": {
        "context": "home",
        "scope": "experiments",
        "image": "registry.example.org/lab/worker@sha256:REPLACE_WITH_DIGEST",
        "entrypoint": "/app/experiment",
        "gpus": "all",
        "timeout_seconds": 600,
        "memory_mb": 8192
      }
    }
  }
}
```

Omit `gpus` for CPU work. `rcc status --provider home` reads containers belonging to the configured scope. `plan` checks the local request. `run` starts the pinned image with the configured deadline. `result` includes the exit code and the tail of stdout. Containers remain available for inspection until their operator removes them. [Docker GPU support](https://docs.docker.com/engine/containers/resource_constraints/#gpu)

## Connect a managed service

Add a profile under `providers` with one of the following driver names and its `config` object. The examples use placeholders for operator resources. Plan and status for these three drivers check local configuration. A live run requires credentials and a provisioned worker that understands your input.

| Driver | Required configuration | Worker input and returned evidence |
| --- | --- | --- |
| `runpod-serverless` | `endpoint_id` for a queue-based endpoint. Set `RUNPOD_API_KEY` in the controller environment. Optional `timeout_seconds` and `ttl_seconds` bound execution and queue lifetime. | Experiment JSON becomes the handler’s `input`. A completed job returns its native status reference and small outputs inline. [RunPod endpoint requests](https://docs.runpod.io/serverless/endpoints/send-requests) |
| `huggingface-jobs` | `namespace`, digest-pinned `image`, `flavor`, `timeout_seconds`, and fixed `command` as an array. Install `huggingface_hub==2.4.0` in the plugin’s Python environment and supply `HF_TOKEN`. | The worker receives `RCC_PARAMS_JSON`. RCC returns the job URL and lifecycle state. Set `artifact_url_template` with a literal `{id}` if your worker saves durable output there. [Hugging Face Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs) |
| `aws-batch` | Full `queue_arn`, revision-pinned `job_definition_arn`, and `timeout_seconds` of at least 60. Install AWS CLI v2 and configure its role/profile. Use a standard-scheduling queue and a single-container job definition. | Include `Ref::rcc_params` as one argument to the approved worker. RCC returns job state, available exit code and CloudWatch log stream. AWS begins the runtime limit when the attempt starts. [AWS Batch parameters](https://docs.aws.amazon.com/batch/latest/userguide/job_definition_parameters.html) |

RunPod and Hugging Face accept a `token_env` setting if you use a different environment variable. Keep credential values out of profile files. A successful managed job may still need its worker to upload results before it exits.

## Write a driver

A custom driver is an executable, in any language, selected by absolute path in the profile’s `driver` field. RCC invokes it once per command. It sends one UTF-8 JSON object over stdin and reads one reply from stdout. The operator supplies `config`. The caller supplies `params`, an optional `why`, or the native `id`. The executable runs as the user invoking RCC.

```json
{"protocol":1,"action":"plan","config":{},"params":{"seed":7}}
```

| Action | Successful reply |
| --- | --- |
| `status` | `{"ok":true,"description":{"workload":"managed-job"}}`, optionally with `running` and `recent` arrays of records with native IDs |
| `plan` | `{"ok":true,"dry":true,"params":{"seed":7}}`. Validate without allocating compute. |
| `run` | `{"ok":true,"stride":{"id":"native-id","status":"running"}}`. Submit once. |
| `result` | `{"ok":true,"stride":{"id":"native-id","status":"done"}}`, with output, an artifact reference or the provider’s failure evidence |

Return `{"ok":false,"refused":"reason"}` for a refusal. Include `"ambiguous":true` when submission may have succeeded. RCC adds the profile name to the run ID. A recovered native receipt can be queried with `rcc result --provider PROFILE NATIVE_ID`. Profiles choose credentials, images and destinations. Job parameters are data.

## Enroll a training provider for Ruu

Ordinary jobs are available by explicit profile name. On scheduled OpenRSI turns, Ruu needs a provider that can enforce a compute budget, run the training workload and return controller-scored evidence. The default Colab broker already does this. An additional profile must opt in with `"resident": true` and advertise `workload: "ruuf.openrsi.v1"`, `families` and `params` dictionaries in its status description. Its run records must follow the existing RUUF training contract, including the parameters, reason, start time and scored arms. The controller evaluates returned predictions against its own held-out answers. [RUUF’s training and scoring contract](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/child/README.md)

Use the bundled `ruuf-broker` driver to connect a second compatible broker with `config` containing its absolute local `socket` path and upstream `kind`. Give it a distinct profile name. Only enroll an independent compute budget once. `rcc status` discovers enrolled training profiles. `rcc providers` lists all configured profiles.
