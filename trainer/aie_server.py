#!/usr/bin/env python
# https://raw.githubusercontent.com/ray-project/ray/releases/0.8.4/rllib/examples/serving/cartpole_server.py
"""
In two separate shells run:
    $ python aie_server.py --run=[PPO|DQN]
    $ python aie_client.py --inference-mode=local|remote
"""

import argparse
import os

import ray
from ray.rllib.agents.dqn import DQNTrainer
from ray.rllib.agents.ppo import PPOTrainer
from ray.rllib.env.policy_server_input import PolicyServerInput
from ray.tune.logger import pretty_print
from regex import D
import yaml

SERVER_ADDRESS = "localhost"
SERVER_PORT = 9900
CHECKPOINT_FILE = "last_checkpoint_{}.out"


def process_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=str, default="PPO")
    parser.add_argument("--run-dir", type=str,
                        help="Path to the directory for this run")

    args = parser.parse_args()
    algo = args.run
    run_directory = args.run_dir

    config_path = os.path.join(args.run_dir, "config.yaml")
    assert os.path.isdir(args.run_dir)
    assert os.path.isfile(config_path)

    with open(config_path, "r") as f:
        run_config = yaml.safe_load(f)

    return algo, run_directory, run_config


def build_trainer(run_config, algo):
    
    
    
    pass


if __name__ == "__main__":
    algo, run_directory, run_config = process_args()

    ray.init()

    env = "CartPole-v0"



    if algo == "DQN":
        # Example of using DQN (supports off-policy actions).
        trainer = DQNTrainer(
            env=env,
            config={
                # Use the connector server to generate experiences.
                "input": (
                    lambda ioctx: PolicyServerInput( \
                        ioctx, SERVER_ADDRESS, SERVER_PORT)
                ),
                # Use a single worker process to run the server.
                "num_workers": 0,
                # Disable OPE, since the rollouts are coming from online clients.
                "input_evaluation": [],
                "exploration_config": {
                    "type": "EpsilonGreedy",
                    "initial_epsilon": 1.0,
                    "final_epsilon": 0.02,
                    "epsilon_timesteps": 1000,
                },
                "learning_starts": 100,
                "timesteps_per_iteration": 200,
                "log_level": "INFO",
            })
    elif algo == "PPO":
        # Example of using PPO (does NOT support off-policy actions).
        trainer = PPOTrainer(
            env=env,

            config={
                # Use the connector server to generate experiences.
                "input": (
                    lambda ioctx: PolicyServerInput( \
                        ioctx, SERVER_ADDRESS, SERVER_PORT)
                ),
                # Use a single worker process to run the server.
                "num_workers": 0,
                # Disable OPE, since the rollouts are coming from online clients.
                "input_evaluation": [],
                "sample_batch_size": 1000,
                "train_batch_size": 4000,
            }
        )
    else:
        raise ValueError("--run must be DQN or PPO")

    checkpoint_path = CHECKPOINT_FILE.format(algo)

    # Attempt to restore from checkpoint if possible.
    if os.path.exists(checkpoint_path):
        checkpoint_path = open(checkpoint_path).read()
        print("Restoring from checkpoint path", checkpoint_path)
        trainer.restore(checkpoint_path)

    # Serving and training loop
    while True:
        print(pretty_print(trainer.train()))
        checkpoint = trainer.save()
        print("Last checkpoint", checkpoint)
        with open(checkpoint_path, "w") as f:
            f.write(checkpoint)