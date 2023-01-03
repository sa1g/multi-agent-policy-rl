import torch
import torch.nn as nn
from gym.spaces import Box, Dict
import numpy as np

# pylint: disable=no-member


def get_flat_obs_size(obs_space):
    """
    Get flat observation size
    """
    if isinstance(obs_space, Box):
        return np.prod(obs_space.shape)
    elif not isinstance(obs_space, Dict):
        raise TypeError

    def rec_size(obs_dict_space, n=0):
        for subspace in obs_dict_space.spaces.values():
            if isinstance(subspace, Box):
                n = n + np.prod(subspace.shape)
            elif isinstance(subspace, Dict):
                n = rec_size(subspace, n=n)
            else:
                raise TypeError
        return n

    return rec_size(obs_space)


def apply_logit_mask1(logits, mask):
    """Mask values of 1 are valid actions."
    " Add huge negative values to logits with 0 mask values."""
    logit_mask = torch.ones(logits.shape) * -10000000
    logit_mask = logit_mask * (1 - mask)

    return logits + logit_mask


class PytorchLinear(nn.Module):
    """A linear (feed-forward) model."""

    def __init__(self, obs_space, action_space, num_outputs, model_config, name):
        super().__init__()
        self.MASK_NAME = "action_mask"
        self.num_outputs = num_outputs
        # mask = obs_space.original_space.spaces[self.MASK_NAME]
        # self.mask_input = nn.Linear(mask.shape[0], mask.shape[1])

        mask = obs_space[self.MASK_NAME]
        self.mask_input = mask.shape

        # Fully connected values:
        self.fc_dim = 128
        self.num_fc = 2

        self.actor = nn.Sequential(
            nn.Linear(
                get_flat_obs_size(obs_space["flat"]), self.fc_dim, dtype=torch.float32
            ),
            nn.ReLU(),
            nn.Linear(self.fc_dim, self.num_outputs),
        )
        # self.actor = apply_logit_mask1(self.logits, self.mask_input)

        # self.actor = apply_logit_mask1(self.actor, self.mask_input)

        # Fully connected Value Function
        # self.fc_layers_val_layers = []# nn.Sequential()

        # for i in range(self.num_fc):
        #     self.fc_layers_val_layers.append(nn.Linear(self.fc_dim, self.fc_dim))
        #     self.fc_layers_val_layers.append(nn.ReLU())

        # self.fc_layers_val_layers.append(nn.Linear(1, self.fc_dim))
        # self.critic = nn.Sequential(*self.fc_layers_val_layers)

        # # self.h_val = self.fc_layers_val

        # # # self.critic = nn.Linear(1, activation=nn.ReLU(), name="critic")(self.h_val)
        # # self.critic = nn.Linear(1, self.h_val)

    def act(self, obs):
        """
        Args:
            obs: agent environment observation

        Returns:
            action: taken action
            action_logprob: log probability of that action
        """
        obs1 = obs["flat"].squeeze().float()
        # obs = obs.long()
        action_probs = self.actor(obs1)
        # print(action_probs.shape)
        # print(obs['action_mask'].shape)
        # sys.exit()
        logit_mask = torch.ones(action_probs.shape) * -10000000
        logit_mask = logit_mask * (1 - obs["action_mask"].squeeze(0))
        action_probs = action_probs + logit_mask

        dist = torch.distributions.Categorical(logits=action_probs)

        action = dist.sample()
        action_logprob = dist.log_prob(action)

        return action.detach(), action_logprob.detach()

    def evaluate(self, obs, act):
        """
        Args:
            obs: agent environment observation
            act: action that is mapped with

        Returns:
            action_logprobs: log probability that `act` is taken with this model
            state_values: value function reward prediction
            dist_entropy: entropy of actions distribution
        """
        action_probs = self.actor(obs)
        dist = torch.distributions.Categorical(action_probs)

        action_logprobs = dist.log_prob(act)
        dist_entropy = dist.entropy()
        state_values = self.critic(obs)

        return action_logprobs, state_values, dist_entropy

    def forward(
        self,
    ):
        """
        Just don't.
        """
        NotImplementedError("Don't use this method.")