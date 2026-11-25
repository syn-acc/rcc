# RCC · Ruu Compute Controller

RCC gives Ruu and its operator one command line for compute. A provider **driver** knows how to run a job on a particular service. A **profile** connects that driver to your own account, queue, endpoint or machine. Choose a profile when you submit an experiment, then use the returned ID to follow it.

| Driver | Where the work runs | What comes back |
| --- | --- | --- |
| Colab | RUUF’s existing, metered Google Colab training workflow | Baseline comparison and controller-scored results |
| Docker | A local engine or remote Docker context, including a home GPU workstation | Container ID, exit status and bounded stdout |
| RunPod Serverless | A preconfigured queue-based endpoint | Native job state and handler output or result reference |
| Hugging Face Jobs | An approved container image on a selected hardware flavor | Job state, native job URL and an optional artifact reference |
| AWS Batch | A configured queue and revision-pinned job definition | Job state, exit code and available CloudWatch log stream |

`./rcc providers` lists installed drivers and configured profiles without contacting any cloud. Colab is the default profile. Configure another provider with the [setup and plugin guide](PROVIDERS.md).

The Colab provider trains and evaluates an open model on a family of tasks. The worker runs on the rented GPU. RUUF keeps the baseline, scores the answers on the controller and enforces the operator’s compute budget. [How the training experiment works](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/child/README.md)

## Try Colab

The controller and Colab client use the Python standard library on Unix. You can run RCC directly from its checkout.

```sh
git clone https://github.com/syn-acc/rcc.git
cd rcc
./rcc --help
```

The following commands need a running RUUF broker and permission to use its Unix socket. The default is `/run/ruu-legs.sock`. Set `RCC_SOCKET` or pass `--socket PATH` for another instance.

```sh
./rcc status
```

Look at `kinds.colab.families` in the JSON reply. Each entry gives a task family, its baseline score and the number of test items. If your broker lists `base_conversion`, you can plan a small experiment with four practice items and five test items.

```sh
echo '{"families":["base_conversion"],"pool":4,"samples":1,"screen":5,"seed":0}' > experiment.json
./rcc plan --provider colab --params experiment.json
```

A successful plan returns the normalized parameters and the command the broker would run. Planning uses no GPU time. If another run is active or the daily limit has been reached, the broker can decline a plan and return its reason in `refused`. To start that experiment against your Colab budget, submit it once.

```sh
./rcc run --provider colab --params experiment.json --why "Compare four practice items against the baseline"
./rcc result RUN_ID
```

Replace `RUN_ID` with `stride.id` from the submission. `result` reports the current state and, on completion, the outcome. If the connection drops during submission, check `./rcc status` before trying again. The broker may already have started the run.

## Running another provider

Once you have configured a profile, use the same four commands. Each worker defines the experiment parameters it accepts.

```sh
rcc status --provider home
rcc plan --provider home --params experiment.json
rcc run --provider home --params experiment.json
rcc result home:NATIVE_ID
```

A profile-qualified ID goes back to the provider that issued it. Existing Colab IDs continue to work as before. If a submission loses its receipt, check the provider’s job list before resubmitting.

For a system install, run `sudo python3 install.py` from the checkout. This installs RCC and its bundled plugins together. [RUUF](https://github.com/syn-acc/ruuf) owns the resident’s research loop, GPU budget and held-out scoring.
