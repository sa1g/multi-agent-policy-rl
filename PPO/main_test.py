from keras_model import build_model
from env_wrapper import RLlibEnvWrapper as EnvWrapper
from tf_models import KerasConvLSTM, get_flat_obs_size
import tensorflow as tf
import numpy as np
from keras_model_base import feed_model, get_model
from ai_economist import foundation
from keras import Model

from tensorflow.python.framework.ops import enable_eager_execution
enable_eager_execution()

model_config = {
    'custom_model': "keras_conv_lstm",
    'custom_options': {
        'fc_dim': 128,
        'idx_emb_dim': 4,
        'input_emb_vocab': 100,
        'lstm_cell_size': 128,
        'num_conv': 2,
        'num_fc': 2,
    },
    'max_seq_len': 25,
}

env_config_wrapper = {
    'env_config_dict': {
        # ===== SCENARIO CLASS =====
        # Which Scenario class to use: the class's name in the Scenario Registry (foundation.scenarios).
        # The environment object will be an instance of the Scenario class.
        'scenario_name':
        'layout_from_file/simple_wood_and_stone',

        # ===== COMPONENTS =====
        # Which components to use (specified as list of ("component_name", {component_kwargs}) tuples).
        #   "component_name" refers to the Component class's name in the Component Registry (foundation.components)
        #   {component_kwargs} is a dictionary of kwargs passed to the Component class
        # The order in which components reset, step, and generate obs follows their listed order below.
        'components': [
            # (1) Building houses
            ('Build', {
                'skill_dist': 'pareto',
                'payment_max_skill_multiplier': 3,
                'build_labor': 10,
                'payment': 10
            }),
            # (2) Trading collectible resources
            ('ContinuousDoubleAuction', {
                'max_bid_ask': 10,
                'order_labor': 0.25,
                'max_num_orders': 5,
                'order_duration': 50
            }),
            # (3) Movement and resource collection
            ('Gather', {
                'move_labor': 1,
                'collect_labor': 1,
                'skill_dist': 'pareto'
            }),
            # (4) Planner
            ('PeriodicBracketTax', {
                'period': 100,
                'bracket_spacing': 'us-federal',
                'usd_scaling': 1000,
                'disable_taxes': False
            })
        ],

        # ===== SCENARIO CLASS ARGUMENTS =====
        # (optional) kwargs that are added by the Scenario class (i.e. not defined in BaseEnvironment)
        'env_layout_file':
        'quadrant_25x25_20each_30clump.txt',
        'starting_agent_coin':
        10,
        'fixed_four_skill_and_loc':
        True,

        # ===== STANDARD ARGUMENTS ======
        # kwargs that are used by every Scenario class (i.e. defined in BaseEnvironment)
        'n_agents':
        4,  # Number of non-planner agents (must be > 1)
        'world_size': [25, 25],  # [Height, Width] of the env world
        'episode_length':
        1000,  # Number of timesteps per episode

        # In multi-action-mode, the policy selects an action for each action subspace (defined in component code).
        # Otherwise, the policy selects only 1 action.
        'multi_action_mode_agents':
        False,
        'multi_action_mode_planner':
        True,

        # When flattening observations, concatenate scalar & vector observations before output.
        # Otherwise, return observations with minimal processing.
        'flatten_observations':
        True,
        # When Flattening masks, concatenate each action subspace mask into a single array.
        # Note: flatten_masks = True is required for masking action logits in the code below.
        'flatten_masks':
        True,

        # How often to save the dense logs
        'dense_log_frequency':
        1
    }
}

env_config = {
    # ===== SCENARIO CLASS =====
    # Which Scenario class to use: the class's name in the Scenario Registry (foundation.scenarios).
    # The environment object will be an instance of the Scenario class.
    'scenario_name': 'layout_from_file/simple_wood_and_stone',
    
    # ===== COMPONENTS =====
    # Which components to use (specified as list of ("component_name", {component_kwargs}) tuples).
    #   "component_name" refers to the Component class's name in the Component Registry (foundation.components)
    #   {component_kwargs} is a dictionary of kwargs passed to the Component class
    # The order in which components reset, step, and generate obs follows their listed order below.
    'components': [
        # (1) Building houses
        ('Build', {'skill_dist': "pareto", 'payment_max_skill_multiplier': 3}),
        # (2) Trading collectible resources
        ('ContinuousDoubleAuction', {'max_num_orders': 5}),
        # (3) Movement and resource collection
        ('Gather', {}),
    ],
    
    # ===== SCENARIO CLASS ARGUMENTS =====
    # (optional) kwargs that are added by the Scenario class (i.e. not defined in BaseEnvironment)
    'env_layout_file': 'quadrant_25x25_20each_30clump.txt',
    'starting_agent_coin': 10,
    'fixed_four_skill_and_loc': True,
    
    # ===== STANDARD ARGUMENTS ======
    # kwargs that are used by every Scenario class (i.e. defined in BaseEnvironment)
    'n_agents': 4,          # Number of non-planner agents (must be > 1)
    'world_size': [25, 25], # [Height, Width] of the env world
    'episode_length': 1000, # Number of timesteps per episode
    
    # In multi-action-mode, the policy selects an action for each action subspace (defined in component code).
    # Otherwise, the policy selects only 1 action.
    'multi_action_mode_agents': False,
    'multi_action_mode_planner': True,
    
    # When flattening observations, concatenate scalar & vector observations before output.
    # Otherwise, return observations with minimal processing.
    'flatten_observations': False,
    # When Flattening masks, concatenate each action subspace mask into a single array.
    # Note: flatten_masks = True is required for masking action logits in the code below.
    'flatten_masks': True,
}

def to_shape(a, shape):
    y_, x_ = shape
    y, x = a.shape
    y_pad = (y_ - y)
    x_pad = (x_ - x)
    return np.pad(a, ((y_pad // 2, y_pad // 2 + y_pad % 2),
                      (x_pad // 2, x_pad // 2 + x_pad % 2)),
                  mode='constant')


def dict_to_tensor_dict(a_dict: dict):
    """
    pass a single agent obs, returns it's tensor_dict
    """
    tensor_dict = {}
    seq_lens = []
    for key, value in a_dict.items():
        # print(f"key: {key}, value: {value}")

        # FLAT DATA
        #tensor_dict[key] = tf.reshape(value, [-1], key)

        # DATA STILL MATRIX
        tensor_dict[key] = tf.convert_to_tensor(value, name=key)
        tensor_dict[key] = tf.expand_dims(tensor_dict[key], axis=0)

        # TEST TO GET seq_lens dinamically (basta scomporre la lista di liste che si genera in una unica lista uni dimensionale.)
        # seq_lens.append(tensor_dict[key].get_shape().as_list())
        # seq_lens.append(tf.shape(tensor_dict[key]))
        # print(f"Tensor KEY: {key}, shape: {tensor_dict[key].get_shape()}")

    #seq_lens = tf.convert_to_tensor(seq_lens)
    # tensor_dict['flat'] = tf.reshape(tensor_dict['flat'], [135])
    return tensor_dict  #, seq_lens

# def concat_dict_tensor(a_dict: dict):
#     """ Concatenates a dict_tensor to a single tensor"""
    
    # for key, value in a_dict.items():


if __name__ == '__main__':
    # FIXME: use ai-economist without rllibenvwrapper
    # env = EnvWrapper(env_config_wrapper)
    
    # env = foundation.make_env_instance(**env_config_wrapper['env_config_dict'])
    env = foundation.make_env_instance(**env_config)
    obs = env.reset()

    model: Model = get_model([16, 32], 3)
    # model.summary()
    # print(dict_to_tensor_dict(obs['0']))
    actions:tf.Tensor = feed_model(dict_to_tensor_dict(obs['0']), model)
    
    print(actions.numpy())
    #print(f"actions: {[i for i in actions]}")
    """
    env.observation_space:
    Dict(
        action_mask:Box(-1e+20, 1e+20, (50,), float32), 
        flat:Box(-1e+20, 1e+20, (136,), float32), 
        time:Box(-1e+20, 1e+20, (1,), float64), 
        world-idx_map:Box(-30178, 30178, (2, 11, 11), int16), 
        world-map:Box(-1e+20, 1e+20, (7, 11, 11), float32)
    )
    action_mask, flat, time, world_idx_map, world-map
    """

    {
        # model = KerasConvLSTM(env.observation_space,
        #                     env.action_space, num_outputs=50, model_config=model_config, name=None)
        # state = model.get_initial_state()

    actions = {'0': 41, '1': 46, '2': 4, '3': 49, 'p': [0]}
    env.step(actions)