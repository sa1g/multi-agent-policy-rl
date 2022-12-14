import numpy as np
import sys
import torch
import torch.nn as nn
from model.model_config import ModelConfig

WORLD_MAP = "world-map"
WORLD_IDX_MAP = "world-idx_map"
ACTION_MASK = "action_mask"


def apply_logit_mask(logits, mask):
    """Mask values of 1 are valid actions."
    " Add huge negative values to logits with 0 mask values."""
    logit_mask = torch.ones(logits.shape) * -10000000
    logit_mask = logit_mask * (1 - mask)
    logit_mask = (logits + logit_mask)

    ## Softmax:
    logit_mask = torch.softmax(logit_mask, dim = 1)

    return logit_mask


class LSTMModel(nn.Module):
    """
    policy&value_function (Actor-Critic) Model
    =====



    """

    def __init__(self, modelConfig: ModelConfig) -> None:
        """
        Initialize the policy&value_function Model.
        """
        super(LSTMModel, self).__init__()
        self.ModelConfig = modelConfig
        # self.logger = get_basic_logger(name, level=log_level, log_path=log_path)
        self.shapes = dict()

        ### This is for managing all the possible inputs without having more networks
        for key, value in self.ModelConfig.observation_space.items():
            ### Check if the input must go through a Convolutional Layer
            if key == ACTION_MASK:
                pass
            elif key == WORLD_MAP:
                self.conv_shape_r, self.conv_shape_c, self.conv_map_channels = (
                    value.shape[1],
                    value.shape[2],
                    value.shape[0],
                )
            elif key == WORLD_IDX_MAP:
                self.conv_idx_channels = value.shape[0] * self.ModelConfig.emb_dim
        ###

        self.embed_map_idx = nn.Embedding(
            self.ModelConfig.input_emb_vocab,
            self.ModelConfig.emb_dim,
            device=self.ModelConfig.device,
            dtype=torch.float32,
        )
        self.conv_layers = nn.ModuleList()
        self.conv_shape = (
            self.conv_shape_r,
            self.conv_shape_c,
            self.conv_map_channels + self.conv_idx_channels,
        )

        for i in range(1, self.ModelConfig.num_conv):
            if i == 1:
                self.conv_layers.append(
                    nn.Conv2d(
                        in_channels=self.conv_shape[1],
                        out_channels=self.ModelConfig.filter[0],
                        kernel_size=self.ModelConfig.kernel_size,
                        stride=self.ModelConfig.strides,
                        # padding_mode='same',
                    )
                )
            self.conv_layers.append(
                nn.Conv2d(
                    in_channels=self.ModelConfig.filter[0],
                    out_channels=self.ModelConfig.filter[1],
                    kernel_size=self.ModelConfig.kernel_size,
                    stride=self.ModelConfig.strides,
                    # padding_mode='same',
                )
            )

        self.conv_dims = (
            self.ModelConfig.kernel_size[0]
            * self.ModelConfig.strides
            * self.ModelConfig.filter[1]
        )
        self.flatten_dims = (
            self.conv_dims
            + self.ModelConfig.observation_space["flat"].shape[0]
            + len(self.ModelConfig.observation_space["time"])
        )
        self.fc_layer_1 = nn.Linear(
            in_features=self.flatten_dims, out_features=self.ModelConfig.fc_dim
        )
        self.fc_layer_2 = nn.Linear(
            in_features=self.ModelConfig.fc_dim, out_features=self.ModelConfig.fc_dim
        )
        self.lstm = nn.LSTM(
            input_size=self.ModelConfig.fc_dim,
            hidden_size=self.ModelConfig.cell_size,
            num_layers=1,
        )
        self.layer_norm = nn.LayerNorm(self.ModelConfig.fc_dim)
        self.output_policy = nn.Linear(
            in_features=self.ModelConfig.cell_size,
            out_features=self.ModelConfig.output_size,
        )
        self.output_value = nn.Linear(
            in_features=self.ModelConfig.cell_size, out_features=1
        )

        self.relu = nn.ReLU()

        self.hidden_state_h_p = torch.zeros(
            1, self.ModelConfig.cell_size, device=self.ModelConfig.device
        )
        self.hidden_state_c_p = torch.zeros(
            1, self.ModelConfig.cell_size, device=self.ModelConfig.device
        )
        self.hidden_state_h_v = torch.zeros(
            1, self.ModelConfig.cell_size, device=self.ModelConfig.device
        )
        self.hidden_state_c_v = torch.zeros(
            1, self.ModelConfig.cell_size, device=self.ModelConfig.device
        )

        self.optimizer = torch.optim.Adam(self.parameters(), lr=self.ModelConfig.lr)

        # self.logger.info("Model created successfully")

    # @time_it
    def forward(self, observation: dict):
        """
        Model's forward. Given an agent observation, action distribution and value function prediction are returned.

        Args:
            observation: agent observation

        Returns:
            logits: actions probability distribution
            value: value function prediction
        """
        if isinstance(observation, dict):
            _world_map = observation[WORLD_MAP]
            _world_idx_map = observation[WORLD_IDX_MAP]
            _flat = observation["flat"]
            _time = observation["time"]
            _action_mask = observation[ACTION_MASK]
        else:
            _world_map = observation[0]
            _world_idx_map = observation[1].long()
            _flat = observation[2]
            _time = observation[3]
            _action_mask = observation[4]

        if self.ModelConfig.name == "p":
            _p0 = observation["p0"]
            _p1 = observation["p1"]
            _p2 = observation["p2"]
            _p3 = observation["p3"]

        conv_input_map = torch.permute(_world_map, (0, 2, 3, 1))
        conv_input_idx = torch.permute(_world_idx_map, (0, 2, 3, 1))

        # Concatenate the remainings of the input
        if self.ModelConfig.name == "p":
            non_convolutional_input = torch.cat(
                [
                    _flat,
                    _time,
                    _p0,
                    _p1,
                    _p2,
                    _p3,
                ],
                axis=1,
            )
        else:
            non_convolutional_input = torch.cat(
                [
                    _flat,
                    _time,
                ],
                axis=1,
            )

        for tag in ["_policy", "_value"]:
            # Embedd from 100 to 4
            map_embedd = self.embed_map_idx(
                conv_input_idx
            )  # TO CHECK WHICH IS THE INPUT -- DONE
            # Reshape the map
            map_embedd = torch.reshape(
                map_embedd,
                (-1, self.conv_shape_r, self.conv_shape_c, self.conv_idx_channels),
            )
            # Concatenate the map and the idx map
            conv_input = torch.cat([conv_input_map, map_embedd], axis=-1)
            # Convolutional Layers
            for conv_layer in self.conv_layers:
                conv_input = self.relu(conv_layer(conv_input))
            # Flatten the output of the convolutional layers
            flatten = torch.reshape(
                conv_input, (-1, self.conv_dims)
            )  # 192 is from 32 * 3 * 2
            # Concatenate the convolutional output with the non convolutional input
            fc_in = torch.cat([flatten, non_convolutional_input], axis=-1)
            # Fully Connected Layers
            for i in range(self.ModelConfig.num_fc):
                if i == 0:
                    fc_in = self.relu(self.fc_layer_1(fc_in))
                else:
                    fc_in = self.relu(self.fc_layer_2(fc_in))
            # Normalize the output
            layer_norm_out = self.layer_norm(fc_in)
            # LSTM

            # Project LSTM output to logits or value
            #
            if tag == "_policy":
                lstm_out, hidden = self.lstm(
                    layer_norm_out, (self.hidden_state_h_p, self.hidden_state_c_p)
                )
                self.hidden_state_h_p, self.hidden_state_c_p = hidden
                logits = apply_logit_mask(self.output_policy(lstm_out), _action_mask)
            else:
                lstm_out, hidden = self.lstm(
                    layer_norm_out, (self.hidden_state_h_v, self.hidden_state_c_v)
                )
                self.hidden_state_h_v, self.hidden_state_c_v = hidden
                value = self.output_value(lstm_out)

        return logits, value

    def fit(self, input, y_true):
        
        

        # Fit the policy network
        output = self.forward(input)
        print(output)

        # Calculate the loss for the policy network
        policy_loss = self.my_loss(output, y_true)

        # Backpropagate the loss
        policy_loss.backward()

        # Update the policy network
        self.optimizer.step()

    def my_loss(self, output, y_true):
        # Calculate the loss for the policy network
        policy_loss = torch.nn.functional.cross_entropy(output, y_true)
        policy_loss._requires_grad = True
        return policy_loss
