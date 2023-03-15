"""
Rollout worker.Manages a policy and creates a batch.
"""
import logging
import sys
from typing import Tuple
# from src.train.ppo import RolloutBuffer
from src.common import EmptyModel
from src.train.ppo import PpoPolicy
from src.train.ppo import save_batch, data_logging
from trainer.utils.rollout_buffer import RolloutBuffer  # , load_batch

# pylint: disable=consider-using-dict-items,consider-iterating-dictionary


class RolloutWorker:
    """
    A lui arriva il solito policies_config che gia' contiene come sono
    impostate le policy e la loro configurazione.
    """

    def __init__(
        self,
        rollout_fragment_length: int,
        batch_iterations: int,
        policies_config: dict,
        mapping_function,
        actor_keys: list,
        env,
        seed: int,
        _id: int = -1,
        experiment_name=None,
    ):
        self.env = env
        self._id = _id

        self.actor_keys = actor_keys
        self.batch_iterations = batch_iterations
        self.rollout_fragment_length = rollout_fragment_length
        self.batch_size = self.batch_iterations * self.rollout_fragment_length
        self.policy_mapping_function = mapping_function
        self.experiment_name = experiment_name

        policy_keys = policies_config.keys()
        env.seed(seed + _id)

        if self._id != -1:
            string = f"{','.join(map(str, policy_keys))}\n"
            data_logging(data=string, experiment_id=self.experiment_name, id=self._id)
        else:
            string = "a_actor_loss,a_critic_loss,p_a_loss,p_c_loss\n"
            data_logging(data=string, experiment_id=self.experiment_name, id=self._id)

        # Build policices
        self.policies = {}
        self.memory = {}
        for key in policy_keys:
            self.policies[key] = self._build_policy(policies_config[key])
            self.memory[key] = RolloutBuffer()

    def _build_policy(self, policy_config: dict):
        if policy_config["policy"] == EmptyModel:
            return EmptyModel(
                observation_space=policy_config["observation_space"],
                action_space=policy_config["action_space"],
            )
        elif policy_config["policy"] == PpoPolicy:
            return PpoPolicy(
                observation_space=policy_config["observation_space"],
                action_space=policy_config["action_space"],
                K_epochs=policy_config["k_epochs"],
                eps_clip=policy_config["eps_clip"],
                gamma=policy_config["gamma"],
                learning_rate=policy_config["learning_rate"],
                c1=policy_config["c1"],
                c2=policy_config["c2"],
                device=policy_config["device"],
                name=policy_config["name"],
            )

    def batch(self):
        """
        Creates a batch of `rollout_fragment_length` steps, save in `self.rollout_buffer`.
        """
        # reset batching environment and get its observation
        obs = self.env.reset()

        # reset rollout_buffer
        for memory in self.memory.values():
            memory.clear()

        for _ in range(self.batch_size):
            # get actions, action_logprob for all agents in each policy* wrt observation
            policy_action, policy_logprob = self.get_actions(obs)

            # get new_observation, reward, done from stepping the environment
            next_obs, rew, done, _ = self.env.step(policy_action)

            if done["__all__"] is True:
                next_obs = self.env.reset()

            # save new_observation, reward, done, action, action_logprob in rollout_buffer
            for _id in self.actor_keys:
                self.memory[self.policy_mapping_function(_id)].update(
                    state=obs[_id],
                    action=policy_action[_id],
                    logprob=policy_logprob[_id],
                    reward=rew[_id],
                    is_terminal=done["__all__"],
                )

            obs = next_obs

        # Dump memory in ram
        save_batch(data=self.memory, worker_id=self._id)

    def get_actions(self, obs: dict) -> Tuple[dict, dict]:
        """
        Build action dictionary using actions taken from all policies.

        Args:
            obs: environment observation

        Returns:
            policy_action
            policy_logprob
        """

        policy_action, policy_logprob = {}, {}

        for key in obs.keys():
            (policy_action[key], policy_logprob[key]) = self.policies[
                self.policy_mapping_function(key)
            ].act(obs[key])

        return policy_action, policy_logprob

    def learn(self, memory):
        """
        TODO: docs
        """
        losses = []
        for key in self.policies:
            losses.append(self.policies[key].learn(rollout_buffer=memory[key]))

        rewards = []
        for _m in losses:
            for _k in _m:
                rewards.append(_k)

        data = f"{','.join(map(str, rewards))}\n"

        data_logging(data=data, experiment_id=self.experiment_name, id=self._id)

    def save_csv(self):
        """
        Append agent's total reward for this batch
        """
        rewards = [sum(m.rewards) for m in self.memory.values()]
        rewards = f"{','.join(map(str, rewards))}\n"

        data_logging(data=rewards, experiment_id=self.experiment_name, id=self._id)

    def get_weights(self) -> dict:
        """
        Get model weights
        """
        weights = {}
        for key in self.policies.keys():
            weights[key] = self.policies[key].get_weights()

        return weights

    def set_weights(self, weights: dict):
        """
        Set model weights
        """
        for key in self.policies.keys():
            self.policies[key].set_weights(weights[key])

    def save_models(self):
        """
        Save the model of each policy.
        """
        for key in self.policies.keys():
            self.policies[key].save_model(name=str(self.experiment_name) + f"/models/{key}.pt")

    def load_models(self, models_to_load:dict):
        """
        Load the model of each policy.

        It doesn't load 'p' policy.
        """
        for key in models_to_load.keys():
            self.policies[key].load_model(models_to_load[key]+f"/models/{key}.pt")

        logging.info("Models loaded!")