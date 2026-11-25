# Compute providers

Store named profiles in `/etc/rcc/providers.json`, or point `--config FILE` or `RCC_CONFIG` at an operator-owned file. The default Colab profile already talks to RUUF’s broker on `/run/ruu-legs.sock`. Its credentials, spending rules and scorer stay with RUUF. [Colab broker](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/legs/runner.py)

## Connect a PC with rccd

Install the bundle with `sudo python3 install.py` from the RCC checkout on the controller and each worker. The worker needs Unix, a running Docker engine and an OpenSSH client. This includes Linux, macOS with Docker Desktop, and a Linux environment under WSL2 with Docker available. Use a Linux Docker engine with device support for GPU work. Each worker dials out, so the home router needs no inbound port.

**On the PC**, pull a CPU smoke-test image and record its local content ID. This example uses the default Docker context. Substitute the output of `docker context show` for `default` below if your engine uses a different context.

```sh
docker pull python:3.12-slim
docker image inspect python:3.12-slim --format '{{.Id}}'
```

Save a worker file such as `worker.json`. Replace `sha256:REPLACE_WITH_LOCAL_IMAGE_ID` with the full ID from the command above. This worker sums a JSON array. An experiment worker uses its own entrypoint and parameter schema.

```json
{
  "providers": {
    "local-worker": {
      "driver": "docker",
      "config": {
        "context": "default",
        "scope": "workstation",
        "image": "sha256:REPLACE_WITH_LOCAL_IMAGE_ID",
        "entrypoint": "/usr/local/bin/python3",
        "args": ["-c", "import json, os; print(sum(json.loads(os.environ['RCC_PARAMS_JSON'])['numbers']))"],
        "timeout_seconds": 30,
        "memory_mb": 256,
        "cpus": 1
      }
    }
  }
}
```

**On the controller**, choose the Unix account that will run RCC. Configure the PC’s SSH alias `rcc-controller` to log in as that account with a key, and verify its host key. Use a socket directory owned by that account with mode `0700`. In this example its home is `/home/compute`. The controller needs OpenSSH server with remote Unix socket forwarding enabled. Use an SSH account you trust each participating PC to access. PCs that share a controller login share its Unix permissions. Add one profile per PC to its RCC configuration:

```json
{
  "providers": {
    "workstation": {"driver": "rccd", "config": {"socket": "/home/compute/rcc-nodes/workstation.sock"}},
    "second-pc":   {"driver": "rccd", "config": {"socket": "/home/compute/rcc-nodes/second-pc.sock"}}
  }
}
```

**On the PC**, start the worker in the foreground. It creates the private socket directory on the controller if the parent exists. Run this same command from your service manager to start it at login or boot. Use a separate socket per PC and a separate worker scope for profiles that share one Docker engine.

```sh
rccd connect --config worker.json --profile local-worker --controller rcc-controller \
  --remote-socket /home/compute/rcc-nodes/workstation.sock
```

**Back on the controller**, exercise the full path:

```sh
printf '%s\n' '{"numbers":[5,7,5]}' > experiment.json
rcc nodes
rcc plan --provider workstation --params experiment.json
rcc run --provider workstation --params experiment.json
rcc result workstation:NATIVE_ID
```

Use the returned `stride.id` in the last command. A completed smoke test returns `stdout_tail` of `17` and exit code zero. `nodes` checks each connection and Docker engine. It reports an offline PC separately and exits nonzero if any configured PC is unavailable. Jobs stay on their named PC. After a disconnect the daemon reconnects and the same ID works while Docker retains the container. For a GPU job, preload the worker’s GPU image, set the appropriate `gpus` selection in its local profile, and use a worker that actually exercises the device. The CPU example needs no GPU. [Docker GPU setup](https://docs.docker.com/engine/containers/resource_constraints/#gpu)

## Connect a Docker engine directly

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

Add a profile under `providers` with one of the following driver names and its `config` object. The examples use placeholders for operator resources. Plan and status for the managed drivers below check local configuration. Online operations require credentials and the provider resources described below.

| Driver | Required configuration | Worker input and returned evidence |
| --- | --- | --- |
| `runpod-serverless` | `endpoint_id` for a queue-based endpoint. Set `RUNPOD_API_KEY` in the controller environment. Optional `timeout_seconds` and `ttl_seconds` bound execution and queue lifetime. | Experiment JSON becomes the handler’s `input`. A completed job returns its native status reference and small outputs inline. [RunPod endpoint requests](https://docs.runpod.io/serverless/endpoints/send-requests) |
| `huggingface-jobs` | `namespace`, digest-pinned `image`, `flavor`, `timeout_seconds`, and fixed `command` as an array. Install `huggingface_hub==2.4.0` in the plugin’s Python environment and supply `HF_TOKEN`. | The worker receives `RCC_PARAMS_JSON`. RCC returns the job URL and lifecycle state. Set `artifact_url_template` with a literal `{id}` if your worker saves durable output there. [Hugging Face Jobs](https://huggingface.co/docs/huggingface_hub/guides/jobs) |
| `aws-batch` | Full `queue_arn`, revision-pinned `job_definition_arn`, and `timeout_seconds` of at least 60. Install AWS CLI v2 and configure its role/profile. Use a standard-scheduling queue and a single-container job definition. | Include `Ref::rcc_params` as one argument to the approved worker. RCC returns job state, available exit code and CloudWatch log stream. AWS begins the runtime limit when the attempt starts. [AWS Batch parameters](https://docs.aws.amazon.com/batch/latest/userguide/job_definition_parameters.html) |
| `kaggle` | `owner`, `scope`, absolute `script`, `script_sha256` and `timeout_seconds`. Set `KAGGLE_API_TOKEN`. CPU and disabled notebook internet are defaults. Optional `machine_shape` and `enable_internet` depend on account access. | Runs the pinned Python worker as a new private notebook with `RCC_PARAMS_JSON`. Returns an owner/slug/version receipt, a version-specific notebook link and a KaggleHub output handle. [Kaggle notebook execution](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md) |
| `kubernetes` | `context`, `namespace`, `scope`, digest-pinned `image`, fixed `command` array, `timeout_seconds`. Install `kubectl` and grant Job create/get in that namespace. Optional `cpu_millis`, `memory_mib`, `gpus` and `gpu_resource`. | Creates one Job with an active deadline. The receipt includes its namespace, name, UID and a Pod log selector. The worker reads `RCC_PARAMS_JSON`. [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/) |
| `skypilot` | `cluster`, `scope`, fixed `command` array starting with an absolute executable, `timeout_seconds`. Install `skypilot==0.14.3` and connect its client to a running SkyPilot API server. Optional `cpus` and `accelerators`. | Runs the preinstalled worker on one existing UP cluster using `sky.exec`. The worker needs GNU `/usr/bin/timeout` and reads `RCC_PARAMS_JSON`. A receipt matches the cluster job number and the RCC job name. [SkyPilot SDK](https://docs.skypilot.ai/en/stable/reference/api.html#sky.exec) |

**Provider coverage.** If you already operate SkyPilot clusters on AWS, Google Cloud, Azure, Oracle Cloud, Lambda, RunPod, Paperspace, Vast.ai, Fluidstack, Cudo or Nebius, configure a separate RCC profile for each cluster you want to use. Cloud provisioning and credentials belong to SkyPilot. Existing GKE, EKS, AKS, CoreWeave or local Kubernetes clusters can also run jobs through the Kubernetes driver with their own context and namespace. Each deployment needs its own worker and a successful run to establish that it works with your account. [SkyPilot infrastructure setup](https://docs.skypilot.ai/en/stable/getting-started/installation.html) · [Kubernetes Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)

Kaggle, RunPod and Hugging Face accept a `token_env` setting if you use a different environment variable. Keep credential values out of profile files. A successful managed job may still need its worker to upload results before it exits.

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
