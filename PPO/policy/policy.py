"""
docs about this file
"""
import copy
import logging
import random
import sys
import time

import numpy as np

# import tensorflow as tf
import torch
from model.model import LSTMModel
from policy.policy_config import PolicyConfig
from utils.timeit import timeit


class PPOAgent:
    """
    PPO Main Optimization Algorithm
    """

    def __init__(self, policy_config: PolicyConfig):
        # Initialization
        # Environment and PPO parameters
        self.policy_config = policy_config
        self.action_space = self.policy_config.action_space  # self.env.action_space.n
        self.max_average = 0  # when average score is above 0 model will be saved
        self.batch_size = self.policy_config.batch_size  # training epochs
        self.shuffle = False

        # # if policy_config is not None:
        # #     self.action_space = policy_config["action_space"]
        # #     self.observation_space:  gym.spaces = policy_config["observation_space"]

        # # Instantiate plot memory
        # self.scores_, self.episodes_, self.average_ = (
        #     [],
        #     [],
        #     [],
        # )  # used in matplotlib plots

        # # Create Actor-Critic network models
        # self.Actor = ActorModel(policy_config.model_config)
        # self.Critic = CriticModel(policy_config.model_config)

        self.Model: LSTMModel = LSTMModel(policy_config.model_config)

    def _obs_dict_to_tensor_list(self, observation: dict):
        """
        Converts a dict of numpy.ndarrays to torch.tensors

        Args:
            observation: Single agent environment observation
        """
        output = []
        for key, value in observation.items():
            output.append(torch.FloatTensor(value).unsqueeze(0)) # pylint: disable=no-member
    
        return output

    @timeit
    def act(self, state):
        """
        Gets an action and vf value from the model.

        Args:
            state: actor state (dict)

        Returns:
            action: single action in [0, self.action_space] from logits distribution
            action_one_hot: one hot encoding for selected action
            logits: actions probabiliy distribution
            value: vf value

        """
        # Use the network to predict the next action to take, using the model
        # Logits: action distribution w/applied mask
        # Value: value function result
        input_state = self._obs_dict_to_tensor_list(state)

        # Get the prediction from the Actor network
        with torch.no_grad():
            logits, value = self.Model(input_state)

        prediction = torch.squeeze(logits)  # pylint: disable=no-member
        action_distribution = torch.distributions.Categorical(prediction) # pylint: disable=no-member
        action = action_distribution.sample()
        
        # One-hot encode the action
        action_onehot = torch.zeros([self.action_space]) # pylint: disable=no-member
        action_onehot[int(action.item())] = 1

        return action, action_onehot, logits, value

    # @timeit
    def _get_gaes(
        self,
        rewards,
        values,
        next_values,
        gamma=0.998,
        lamda=0.98,
        normalize=True,
    ):
        """
        Gae's calculation
        Removed dones
        """
        deltas = [r + gamma * nv - v for r, nv, v in zip(rewards, next_values, values)]
        deltas = np.stack(deltas)
        gaes = copy.deepcopy(deltas)

        for t in reversed(range(len(deltas) - 1)):
            gaes[t] = gaes[t] + gamma * lamda * gaes[t + 1]

        target = gaes + values

        if normalize:
            gaes = (gaes - gaes.mean()) / (gaes.std() + 1e-8)

        return np.vstack(gaes), np.vstack(target)

    def learn(
        self,
        observations: list,
        next_observations: list,
        policy_actions: list,
        policy_predictions: list,
        rewards: list,
        vf_predictions: list,
        vf_predictions_old: list,
    ):
        """
        Train Policy networks
        """

        EPSYLON = 0.2           # pylint: disable = invalid-name
        ENTROPY_LOSS = 0.001    # pylint: disable = invalid-name



        # # Compute discounted rewards and advantages
        # # GAE
        logging.debug("Calculating gaes")
        advantages, target = self._get_gaes(
            rewards, np.squeeze(vf_predictions_old), np.squeeze(vf_predictions)
        )

        # pi = actions_one_hot [0,50] * actions_prediction_distribution
        # pi_old = actions_one_hot [0,50] * old_actions_prediction_distribution
        # print(type(policy_predictions))
        # sys.exit()

        y_pred = [np.zeros((1,50))] + policy_predictions[1:]
        prob = torch.tensor(policy_actions * policy_predictions)
        old_prob = torch.tensor(policy_actions * y_pred)

        

        prob = torch.clip(prob, 1e-10, 1.0)
        old_prob = torch.clip(old_prob, 1e-10, 1.0)

        ratio = torch.exp(
            torch.log(prob) - torch.log(old_prob)
        )

        p1 = ratio * torch.tensor(advantages)

        p2 = torch.clip(ratio, max=(1 + EPSYLON), min=(1 - EPSYLON)) * advantages

        actor_loss = -torch.mean(torch.minimum(p1, p2))

        # critic_loss = # TODO

        # entropy = list()
        # for x in y_pred:
        #     print(f"DIO {x}")
        #     x += 1e-10
        #     print(f"CANE {x}")
        #     entropy.append(-(x * np.log(x)))

        # entropy = torch.from_numpy(np.array(entropy))
        # entropy = ENTROPY_LOSS * torch.mean(entropy)

        entropy = []
        for x in y_pred:
            entropy.append(-(x * np.log(x)))
            print(np.log(x))
            # print(np.log(torch.tensor([-10000000])))
        # print(y_pred)
        # # print(entropy)
        # sys.exit()
        # entropy = -(y_pred * torch.log(y_pred))
        entropy = ENTROPY_LOSS * torch.mean(torch.tensor(np.array(entropy)))

        total_loss = actor_loss - entropy

        total_loss = actor_loss - entropy
        print(total_loss)
        # print(advantages.shape)
        # print(vf_predictions.shape)
        # print(policy_actions.shape)
        # print(target.shape)
        # sys.exit()

        # y_true = [advantages, vf_predictions, policy_actions, target]

        # # FIT
        # self.Model.fit(observations, y_true)

        # values = self.Critic.batch_predict(observations)
        # next_values = self.Critic.batch_predict(next_observations)

        # logging.debug(f"     Values and next_values required {time.time()-tempo}s")

        # # Compute discounted rewards and advantages
        # # GAE
        # tempo = time.time()

        # advantages, target = self._get_gaes(
        #     rewards, np.squeeze(values), np.squeeze(next_values)
        # )

        # logging.debug(f"     Gaes required {time.time()-tempo}s")

        # # stack everything to numpy array
        # # pack all advantages, predictions and actions to y_true and when they are received
        # # in custom PPO loss function we unpack it
        # tempo = time.time()
        # y_true = np.hstack([advantages, vf_predictions, policy_actions])
        # logging.debug(f"     Data prep required: {time.time()-tempo}s")

        # tempo = time.time()

        # # training Actor and Critic networks
        # a_loss = self.Actor.actor.fit(
        #     [world_map, flat],
        #     y_true,
        #     # batch_size=self.batch_size,
        #     epochs=self.policy_config.agents_per_possible_policy
        #     * self.policy_config.num_workers,
        #     steps_per_epoch=self.batch_size // self.policy_config.num_workers,
        #     verbose=0,
        #     shuffle=self.shuffle,
        #     workers=8,
        #     use_multiprocessing=True,
        # )
        # logging.debug(f"     Fit Actor Network required {time.time()-tempo}s")
        # logging.debug(f"        Actor loss: {a_loss.history['loss'][-1]}")

        # tempo = time.time()
        # values = tf.convert_to_tensor(values)
        # target = [target, values]
        # logging.debug(f"    Prep 2 required {time.time()-tempo}")

        # tempo = time.time()
        # c_loss = self.Critic.critic.fit(
        #     [world_map, flat],
        #     target,
        #     # batch_size=self.batch_size,
        #     epochs=1,
        #     steps_per_epoch=self.batch_size,
        #     verbose=0,
        #     shuffle=self.shuffle,
        #     workers=8,
        #     use_multiprocessing=True,
        # )
        # logging.debug(f"     Fit Critic Network required {time.time()-tempo}s")

        # logging.debug(f"        Critic loss: {c_loss.history['loss'][-1]}")

    # def _load(self) -> None:
    #     """
    #     Save Actor and Critic weights'
    #     """
    #     self.Actor.actor.load_weights(self.Actor_name)
    #     self.Critic.critic.load_weights(self.Critic_name)

    # def _save(self) -> None:
    #     """
    #     Load Actor and Critic weights'
    #     """
    #     self.Actor.actor.save_weights(self.Actor_name)
    #     self.Critic.critic.save_weights(self.Critic_name)

    def _policy_mapping_fun(self, i: str) -> str:
        """
        Use it by passing keys of a dictionary to differentiate between agents

        default for ai-economist environment:
        returns a if `i` is a number -> if the key of the dictionary is a number,
        returns p if `i` is a string -> social planner
        """
        if str(i).isdigit() or i == "a":
            return "a"
        return "p"
