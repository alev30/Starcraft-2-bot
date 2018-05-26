import random
import math

import numpy as np
import pandas as pd

from pysc2.agents import base_agent
from pysc2.lib import actions
from pysc2.lib import features

_NO_OP = actions.FUNCTIONS.no_op.id
_SELECT_POINT = actions.FUNCTIONS.select_point.id
_BUILD_SUPPLY_DEPOT = actions.FUNCTIONS.Build_SupplyDepot_screen.id
_BUILD_BARRACKS = actions.FUNCTIONS.Build_Barracks_screen.id
_TRAIN_MARINE = actions.FUNCTIONS.Train_Marine_quick.id
_SELECT_ARMY = actions.FUNCTIONS.select_army.id
_ATTACK_MINIMAP = actions.FUNCTIONS.Attack_minimap.id
_MOVE_MINIMAP = actions.FUNCTIONS.Move_minimap.id

_PLAYER_RELATIVE = features.SCREEN_FEATURES.player_relative.index
_UNIT_TYPE = features.SCREEN_FEATURES.unit_type.index
_PLAYER_ID = features.SCREEN_FEATURES.player_id.index
_PLAYER_RELATIVE_MINI = features.MINIMAP_FEATURES.player_relative.index
_MINI_VISIBILITY = features.MINIMAP_FEATURES.visibility_map.index

_PLAYER_SELF = 1
_PLAYER_ENEMY = 4

_VISIBLE = 1

_TERRAN_COMMANDCENTER = 18
_TERRAN_SCV = 45
_TERRAN_SUPPLY_DEPOT = 19
_TERRAN_BARRACKS = 21

_NOT_QUEUED = [0]
_QUEUED = [1]


ACTION_DO_NOTHING = 'donothing'
ACTION_SELECT_SCV = 'selectscv'
ACTION_BUILD_SUPPLY_DEPOT = 'buildsupplydepot'
ACTION_BUILD_BARRACKS = 'buildbarracks'
ACTION_SELECT_BARRACKS = 'selectbarracks'
ACTION_BUILD_MARINE = 'buildmarine'
ACTION_SELECT_ARMY = 'selectarmy'
#ACTION_ATTACK = 'attack'
ACTION_SCOUT = 'scout'

smart_actions = [
    ACTION_DO_NOTHING,
    ACTION_SELECT_SCV,
    ACTION_BUILD_SUPPLY_DEPOT,
   # ACTION_BUILD_BARRACKS,
    ACTION_SELECT_BARRACKS,
    ACTION_BUILD_MARINE,
    #ACTION_SELECT_ARMY,
    ACTION_SCOUT,
]
# add in a scout for every single location on the map split into 4 quadrants
for mm_x in range(0, 64):
    for mm_y in range(0, 64):
        if (mm_x + 1) % 16 == 0 and (mm_y + 1) % 16 == 0:
            smart_actions.append(ACTION_SCOUT + '__' + str(mm_x - 8) + '__' + str(mm_y - 8))


SEE_ENEMY_REWARD = 0.5
NOT_DIE_REWARD = 0.5


# Stolen from https://github.com/MorvanZhou/Reinforcement-learning-with-tensorflow
class QLearningTable:
    def __init__(self, actions, learning_rate=0.01, reward_decay=0.9, e_greedy=0.9):
        self.actions = actions
        self.lr = learning_rate
        self.gamma = reward_decay
        self.epsilon = e_greedy
        self.q_table = pd.DataFrame(columns=self.actions, dtype=np.float64)

    def choose_action(self, observation):
        self.check_state_exist(observation)

        if np.random.uniform() < self.epsilon:
            # choose best action
            state_action = self.q_table.ix[observation, :]

            # some actions have the same value
            state_action = state_action.reindex(np.random.permutation(state_action.index))

            action = state_action.idxmax()
        else:
            # choose random action
            action = np.random.choice(self.actions)

        return action

    def learn(self, s, a, r, s_):
        self.check_state_exist(s_)
        self.check_state_exist(s)

        q_predict = self.q_table.ix[s, a]
        q_target = r + self.gamma * self.q_table.ix[s_, :].max()

        # update
        self.q_table.ix[s, a] += self.lr * (q_target - q_predict)

    def check_state_exist(self, state):
        if state not in self.q_table.index:
            # append new state to q table
            self.q_table = self.q_table.append(
                pd.Series([0] * len(self.actions), index=self.q_table.columns, name=state))



class SmartAgent(base_agent.BaseAgent):
    def transformDistance(self, x, x_distance, y, y_distance):
        if not self.base_top_left:
            return [x - x_distance, y - y_distance]

        return [x + x_distance, y + y_distance]

    def transformLocation(self, x, y):
        if not self.base_top_left:
            return [63 - x, 63 - y]

        return [x, y]

    def __init__(self):
        super(SmartAgent,self).__init__()
        self.qlearn = QLearningTable(actions=list(range(len(smart_actions))))
        self.previous_action = None
        self.previous_state = None
        self.previousEnemyxy = []
        self.previousSupply = 0
        self.selectSCV = False
        self.barracksBuilt = False
        self.selectArmy = False
        self.count = 0
        self.previousVisible = [[0],[0]]

    def step(self, obs):
        super(SmartAgent, self).step(obs)

        if obs.first():
            player_y, player_x = (obs.observation['minimap'][_PLAYER_RELATIVE] == _PLAYER_SELF).nonzero()
            self.SelectSCV = False
            self.barracksBuilt = False
            self.selectArmy = False
            self.base_top_left = 1 if player_y.any() and player_y.mean() <= 31 else 0
            self.previousVisible = (obs.observation['minimap'][_MINI_VISIBILITY] == _VISIBLE).nonzero()

        #############SETTING UP THE STATE#############
        unit_type = obs.observation['screen'][_UNIT_TYPE]
        enemy_y, enemy_x = (obs.observation['minimap'][_PLAYER_RELATIVE_MINI] == _PLAYER_ENEMY).nonzero()
        visible = (obs.observation['minimap'][_MINI_VISIBILITY] == _VISIBLE).nonzero()


        enemyXY = [enemy_x.mean(), enemy_y.mean()]

        depot_y, depot_x = (unit_type == _TERRAN_SUPPLY_DEPOT).nonzero()
        supply_depot_count = 1 if depot_y.any() else 0

        barracks_y, barracks_x = (unit_type == _TERRAN_BARRACKS).nonzero()
        barracks_count = 1 if barracks_y.any() else 0

        supply_limit = obs.observation['player'][4]
        army_supply = obs.observation['player'][8]

        current_state = [
            supply_depot_count,
            barracks_count,
            supply_limit,
            army_supply,
            #enemyXY,
            visible,
        ]
        ################################################

            #Dont learn from the first step#
        if self.previous_action is not None:
            reward = 0
            #Adjust reward based on current score
           # if enemyXY is not self.previousEnemyxy and enemy_x.any():
            if (len(visible[0]) + len(visible[1])) - (len(self.previousVisible[0]) + len(self.previousVisible[1])) >= 17:
                if army_supply >= 0:
                    print((len(visible[0]) + len(visible[1])) - (len(self.previousVisible[0]) + len(self.previousVisible[1])))
                    reward += SEE_ENEMY_REWARD
                   # reward += NOT_DIE_REWARD
            self.qlearn.learn(str(self.previous_state),self.previous_action,reward,str(current_state))


                #Choose an action#
        rl_action = self.qlearn.choose_action(str(current_state))
        if self.count % 3 is 0:
            smart_action = smart_actions[rl_action]
        else:
            smart_action = ACTION_DO_NOTHING

        self.count = self.count + 1
                #Set up state for next step#
        self.previous_state = current_state
        self.previous_action = rl_action
        self.previousEnemyxy = enemyXY
        self.previousSupply = army_supply
        self.previousVisible = visible
        # get the x and y coords if its a scout action
        x = 0
        y = 0
        if '__' in smart_action:
            smart_action, x, y = smart_action.split('__')

                #Perform the selected actions#
        if smart_action == ACTION_DO_NOTHING:
            return actions.FunctionCall(_NO_OP,[])

        elif smart_action == ACTION_SELECT_SCV and not self.barracksBuilt:
            unit_type = obs.observation['screen'][_UNIT_TYPE] #Put all units on screen into unit_type
            unit_y,unit_x = (unit_type == _TERRAN_SCV).nonzero() #select all the x and y coords of terran scv
            if unit_y.any():
                i = random.randint(0,len(unit_y)-1)
                target = [unit_x[i],unit_y[i]]
                self.selectSCV = True
                return actions.FunctionCall(_SELECT_POINT,[_NOT_QUEUED,target])

        elif smart_action == ACTION_BUILD_SUPPLY_DEPOT:
            if _BUILD_SUPPLY_DEPOT in obs.observation['available_actions']:
                unit_type = obs.observation['screen'][_UNIT_TYPE]
                unit_y, unit_x = (unit_type == _TERRAN_COMMANDCENTER).nonzero()

                if unit_y.any():
                    target = self.transformDistance(int(unit_x.mean()), 0, int(unit_y.mean()), 20)

                    return actions.FunctionCall(_BUILD_SUPPLY_DEPOT, [_NOT_QUEUED, target])


        elif smart_action == ACTION_SELECT_BARRACKS:
            unit_type = obs.observation['screen'][_UNIT_TYPE]
            unit_y, unit_x = (unit_type == _TERRAN_BARRACKS).nonzero()

            if unit_y.any():
                target = [int(unit_x.mean()), int(unit_y.mean())]
                self.selectArmy = False
                self.selectSCV = False
                return actions.FunctionCall(_SELECT_POINT, [_NOT_QUEUED, target])

        elif smart_action == ACTION_BUILD_MARINE:
            if _TRAIN_MARINE in obs.observation['available_actions']:
                return actions.FunctionCall(_TRAIN_MARINE, [_QUEUED])
            elif _BUILD_BARRACKS in obs.observation['available_actions'] and not self.barracksBuilt:
                unit_type = obs.observation['screen'][_UNIT_TYPE]
                unit_y, unit_x = (unit_type == _TERRAN_COMMANDCENTER).nonzero()
                if unit_y.any():
                    target = self.transformDistance(int(unit_x.mean()), 20, int(unit_y.mean()), 0)
                    self.barracksBuilt = True
                    return actions.FunctionCall(_BUILD_BARRACKS, [_NOT_QUEUED, target])


        elif smart_action == ACTION_SCOUT and not self.selectSCV:
            if _SELECT_ARMY in obs.observation['available_actions'] and not self.selectArmy:
                self.selectSCV = False
                self.selectArmy = True
                return actions.FunctionCall(_SELECT_ARMY, [_NOT_QUEUED])
            elif _MOVE_MINIMAP in obs.observation["available_actions"]:
                target = self.transformLocation(int(x),int(y))
                return actions.FunctionCall(_MOVE_MINIMAP,[_NOT_QUEUED,target])



        return actions.FunctionCall(_NO_OP, [])



