# RCC · Ruu Compute Controller

RCC gives Ruu a command line for remote experiments. From the machine running the broker, you can see which experiments it accepts, check a proposed run, submit it and look up the result by ID. The first provider uses Google Colab through [RUUF’s compute broker](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/legs/runner.py).

The Colab provider trains and evaluates an open model on a family of tasks. The worker runs on the rented GPU. RUUF keeps the baseline, scores the answers on the controller and enforces the operator’s compute budget. [How the training experiment works](https://github.com/syn-acc/ruuf/blob/main/ruu-lab/child/README.md)

## Try a dry run

RCC runs on a Unix system with Python 3. There are no packages to install.

```sh
git clone https://github.com/syn-acc/rcc.git
cd rcc
chmod +x rcc
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

## Where this is going

The next provider is an operator-owned machine, such as a home GPU workstation. The goal is to take the same experiment file to either provider and bring the result back for scoring. This release supports Colab through an existing RUUF installation. Workstation enrollment and general notebook execution are planned.

[RUUF](https://github.com/syn-acc/ruuf) is the resident framework that gives Ruu its workspace, memory and research loop. RCC is its independently usable compute client.
