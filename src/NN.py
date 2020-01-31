from __future__ import absolute_import, division, print_function, unicode_literals
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

from gamedata import GameDataAPI as gd
from controller import BasicController as bc
from controller import keymonitor as km

import math as m
import sys, os, platform, subprocess
import numpy as np
import pygame
import cv2
import tensorflow as tf
from tensorflow import keras
pygame.init()

''' Colour triples '''
WHITE = (255,255,255)
BLACK = (0,0,0)

''' Control constants '''
START_RES = (500,500)
IMG_SIZE = (60,50)
INVGAPSIZE = 14    # Inverse of player to opponent gap size (Low => Longer gap, High => Shorter gap)
OUT_THRESH = 0.5

''' Control variables '''
gameInit = False
pause = False
visualise = len(sys.argv) >= 2 and int(sys.argv[1]) == 1
NNmode = 0  # 0 - Vanilla mode, 1 - RNN mode, 2 - LSTM mode

''' Game variables '''
playerMaxStock = 0
oppMaxStock = 0

''' Hyperparameters '''
input_width = 3094
hidden_layers = [2048, 1024, 128]
output_width = 11
# Data type of numpy arrays and tensorflow layers and tensors
tf_dtype = tf.float32
np_dtype = np.float32


# Generate 2 images, the player to platforms and the player to opponent
def getImg():
    stageRes = (gd.cambounds()["x1"], gd.cambounds()["y1"])

    ''' Player to platforms image '''
    # Create surfaces for drawing platforms and characters
    plat_img = pygame.Surface(stageRes)
    # Empty space is black
    plat_img.fill(BLACK)
    # Draw platforms for plat_img
    for t in gd.terrain():
        plat_img.blit(t.img, t.pos)
    for p in gd.platforms():
        pygame.draw.rect(plat_img, WHITE, pygame.Rect(p["x"],p["y"],p["w"],p["h"]))
    # Draw player in plat_img
    pygame.draw.rect(plat_img, (128, 128, 128), pygame.Rect(gd.player.pos, gd.player.dim))
    # Scale images to fit required dimensions
    plat_img = pygame.transform.scale(plat_img, IMG_SIZE)
    # Normalise pixel values to 0.0 - 1.0 range
    plat_img_array = pygame.surfarray.array2d(plat_img).swapaxes(0,1) / 16777215.0

    ''' Opponent to player image '''
    # Create surfaces for drawing platforms and characters
    opp_img = pygame.Surface(stageRes)
    # Empty space is black
    opp_img.fill(BLACK)
    # Draw opponent in opp_img
    pygame.draw.rect(opp_img, WHITE, pygame.Rect(gd.opponent.pos, gd.opponent.dim))
    # Draw player in opp_img
    pygame.draw.rect(opp_img, (128, 128, 128), pygame.Rect(gd.player.pos, gd.player.dim))
    # Scale images to fit required dimensions
    opp_img = pygame.transform.scale(opp_img, IMG_SIZE)
    # Normalise pixel values to 0.0 - 1.0 range
    opp_img_array = pygame.surfarray.array2d(opp_img).swapaxes(0,1) / 16777215.0

    ''' Opponent to player data array '''
    oppRect = pygame.Rect(gd.opponent.pos, gd.opponent.dim)
    playRect = pygame.Rect(gd.player.pos, gd.player.dim)
    oppToPlayer = np.array( \
        [max(0, 1 - INVGAPSIZE*max(0,oppRect.left - playRect.right)/stageRes[0]), \
        max(0, 1 - INVGAPSIZE*max(0,playRect.left - oppRect.right)/stageRes[0]), \
        max(0, 1 - INVGAPSIZE*max(0,oppRect.top - playRect.bottom)/stageRes[1]), \
        max(0, 1 - INVGAPSIZE*max(0,playRect.top - oppRect.bottom)/stageRes[1])]  \
    )

    return (plat_img_array, opp_img_array, oppToPlayer)

# Generate array of data concerning passed game character (player or opponent)
def getCharDataArray(character):
    # Continuous inputs
    data = np.array( \
        # Stock
        [character.lives/playerMaxStock,   \
        # Damage taken
        m.tanh(character.damage/100),    \
        # Shield power
        character.shieldPow/100,       \
        # Horizontal distance from left stage boundary
        (character.pos[0] - gd.deathbounds()["x0"])/(gd.deathbounds()["x1"] - gd.deathbounds()["x0"]),  \
        # Horizontal distance from right stage boundary
        (gd.deathbounds()["x1"] - character.pos[0])/(gd.deathbounds()["x1"] - gd.deathbounds()["x0"]),  \
        # Vertical distance from up stage boundary
        (character.pos[1] - gd.deathbounds()["y0"])/(gd.deathbounds()["y1"] - gd.deathbounds()["y0"]),  \
        # Vertical distance from down stage boundary
        (gd.deathbounds()["y1"] - character.pos[1])/(gd.deathbounds()["y1"] - gd.deathbounds()["y0"])  \
        ]   \
    )
    # Binary inputs
    data = np.append(data, \
        [character.shielding,   \
        character.attacking,    \
        character.onLand,       \
        character.crouching,    \
        character.onLedge,      \
        character.grabbing,     \
        character.dodging,      \
        character.dizzy,        \
        character.knocked_down, \
        character.invincible,   \
        character.ko,           \
        character.dashing,      \
        character.facing_right  \
        ]                       \
    )
    # Attack inputs (Also Binary)
    data = np.append(data, \
        [                   \
            # Neutral A
            character.attack == "a",   \
            # Down A
            character.attack == "crouch_attack",   \
            # Side A
            character.attack == "a_forward_tilt",   \
            # Dash A
            character.attack == "a_forward",   \
            # Up A
            character.attack == "a_up_tilt",     \

            # Down Smash
            character.attack == "a_down",     \
            # Side Smash
            character.attack == "a_forwardsmash",     \
            # Up Smash
            character.attack == "a_up",     \

            # Neutral A Air
            character.attack == "a_air",     \
            # Forward A air
            character.attack == "a_air_forward",     \
            # Back A air
            character.attack == "a_air_backward",     \
            # Up A air
            character.attack == "a_air_up",     \
            # Down A air
            character.attack == "a_air_down",     \

            # Neutral B
            character.attack == "b",     \
            # Down B
            character.attack == "b_down",     \
            # Side B
            character.attack == "b_forward",     \
            # Up B
            character.attack == "b_up",     \

            # Neutral B air
            character.attack == "b_air",     \
            # Up B air
            character.attack == "b_up_air",     \
            # Side B air
            character.attack == "b_forward_air",     \
            # Down B air
            character.attack == "b_down_air",     \

            # Throw down
            character.attack == "throw_down",     \
            # Throw forward
            character.attack == "throw_forward",     \
            # Throw backward
            character.attack == "throw_back",     \
            # Throw Up
            character.attack == "throw_up"     \
        ]                   \
    )

    return data


'''Main driver code'''
if __name__ == "__main__":
    print("Waiting for SSF2 to connect")
    # Windows
    if platform.release() in ("Vista", "7", "8", "9", "10"):
        subprocess.Popen(["..\\SSF2-win\\SSF2.exe"])
    else:
        # Linux
        os.chdir("../SSF2-linux/")
        subprocess.Popen("./SSF2", stderr=subprocess.DEVNULL)
    gd.startAPI()
    # Keyboard listener
    keylistener = km.start_listener()



    ''' Vanilla NN mode '''
    if NNmode == 0:
        NNmodel = keras.models.Sequential()
        NNmodel.add(keras.layers.Dense(hidden_layers[0], input_shape=(input_width,), dtype=tf_dtype))
        # Build the rest of the Feed-Forward NN
        for l in range(len(hidden_layers)-1):
            NNmodel.add(keras.layers.Dense(hidden_layers[l+1], input_shape=(hidden_layers[l],), activation="relu", use_bias=True, dtype=tf_dtype))
        NNmodel.add(keras.layers.Dense(output_width, input_shape=(hidden_layers[-1],), activation="sigmoid", use_bias=True, dtype=tf_dtype))
        NNmodel.compile(optimizer='adam',
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        ''' RNN mode '''
    elif NNmode == 1:
        NNmodel = keras.models.Sequential()
        RNNmodel = keras.layers.SimpleRNN(hidden_layers[0], return_state=True, dtype=tf_dtype)
        hidden_state = tf.zeros([1,hidden_layers[0]],dtype=tf_dtype)   # Initial short term memory state
        # Build the rest of the Feed-Forward NN
        for l in range(len(hidden_layers)-1):
            NNmodel.add(keras.layers.Dense(hidden_layers[l+1], input_shape=(hidden_layers[l],), activation="relu", use_bias=True, dtype=tf_dtype))
        NNmodel.add(keras.layers.Dense(output_width, input_shape=(hidden_layers[-1],), activation="sigmoid", use_bias=True, dtype=tf_dtype))
        NNmodel.compile(optimizer='adam',
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )
        ''' LSTM mode '''
    elif NNmode == 2:
        NNmodel = keras.models.Sequential()
        LSTMmodel = keras.layers.LSTM(hidden_layers[0], return_state=True, dtype=tf_dtype)
        h_state = tf.zeros([1,hidden_layers[0]],dtype=tf_dtype) # Initial short term memory state
        c_state = tf.zeros([1,hidden_layers[0]],dtype=tf_dtype) # Initial long term memory state
        # Build the rest of the Feed-Forward NN
        for l in range(len(hidden_layers)-1):
            NNmodel.add(keras.layers.Dense(hidden_layers[l+1], input_shape=(hidden_layers[l],), activation="relu", use_bias=True, dtype=tf_dtype))
        NNmodel.add(keras.layers.Dense(output_width, input_shape=(hidden_layers[-1],), activation="sigmoid", use_bias=True, dtype=tf_dtype))
        NNmodel.compile(optimizer='adam',
            loss='categorical_crossentropy',
            metrics=['accuracy']
        )



    while gd.isActive():

        if gd.inGame():
            gd.updateAPI()
            # Initialise stuff when starting game
            if not gameInit:
                playerMaxStock = gd.player.lives
                oppMaxStock = gd.opponent.lives
                gameInit = True

            ''' Player data '''
            playerData = getCharDataArray(gd.player)
            ''' Opponent data '''
            oppData = getCharDataArray(gd.opponent)
            ''' Image data '''
            platimg, oppimg, oppToPlayer = getImg()
            platimg = np.reshape(platimg, -1)
            oppimg = np.reshape(oppimg, -1)
            imgs = np.concatenate((platimg,), axis=None)
            ''' Joining data together '''
            NNinput = np.concatenate((playerData, oppData, platimg, oppToPlayer))
            NNinput = NNinput.astype(np_dtype)  # Convert to standard data type

            ''' Feed forward inputs '''
            # Vanilla
            if NNmode == 0:
                NNinput = np.reshape(NNinput, (1,-1))   # Reshape input to 2D array
                output = np.reshape(NNmodel.predict(NNinput), (-1,))    # Reshape output into 1D array
            # RNN
            elif NNmode == 1:
                NNinput = np.reshape(NNinput, (1, 1,-1))   # Reshape input to (1 batch, 1 timestep, features)
                RNNoutput, hidden_state = RNNmodel(NNinput, initial_state=[hidden_state])   # Feed current inputs , as well as previous hidden state
                output = np.reshape(NNmodel.predict(RNNoutput.numpy()), (-1,))    # Reshape output into 1D array
            # LSTM
            elif NNmode == 2:
                NNinput = np.reshape(NNinput, (1, 1,-1))   # Reshape input to (1 batch, 1 timestep, features)
                LSTMoutput, h_state, c_state = LSTMmodel(NNinput, initial_state=[h_state, c_state])
                output = np.reshape(NNmodel.predict(LSTMoutput.numpy()), (-1,))    # Reshape output into 1D array

            ''' Apply game inputs '''
            # Press key if corresponding output is past threshold
            keystate = {
                "w":output[0] > OUT_THRESH,
                "a":output[1] > OUT_THRESH,
                "s":output[2] > OUT_THRESH,
                "d":output[3] > OUT_THRESH,
                "e":output[4] > OUT_THRESH,
                "f":output[5] > OUT_THRESH,
                "p":output[6] > OUT_THRESH,
                "o":output[7] > OUT_THRESH,
                "i":output[8] > OUT_THRESH,
                "l":output[9] > OUT_THRESH,
                "k":output[10] > OUT_THRESH
            }
            if platform.release() in ("Vista", "7", "8", "9", "10"):
                os.system("cls")
            else:
                os.system("clear")
            print(output)
            bc.applyKeyState(keystate)

            ''' Visualise '''
            if visualise:
                ''' Show inputs '''
                dataview = np.concatenate((playerData, oppData, oppToPlayer))
                for i in range(dataview.size % IMG_SIZE[0], IMG_SIZE[0]):
                    dataview = np.append(dataview, 0)
                view = np.concatenate((imgs, dataview))
                view = np.reshape(view, (-1,IMG_SIZE[0]))
                cv2.imshow("inputs", cv2.resize(view, dsize=(view.shape[1]*5, view.shape[0]*5), interpolation=cv2.INTER_AREA))

                ''' Show layers '''
                # RNN output
                if NNmode == 1:
                    rnnarray = RNNoutput.numpy()
                    if rnnarray.size % 100 != 0:
                        for i in range(rnnarray.size % 100, 100):
                            rnnarray = np.append(rnnarray, 0)
                    rnnarray = np.reshape(rnnarray, (-1, 100))
                    cv2.imshow("RNN", cv2.resize(rnnarray, dsize=(rnnarray.shape[1]*5, rnnarray.shape[0]*5), interpolation=cv2.INTER_AREA))
                # Each hidden layer in NNmodel
                # for l in range(len(hidden_layers)):
                #     print(l)
                #     layerarray = NNmodel.get_layer(index=l).output.eval()
                #     if layerarray.size % 100 != 0:
                #         for i in range(layerarray.size % 100, 100):
                #             layerarray = np.append(layerarray, 0)
                #     layerarray = np.reshape(layerarray, (-1, 100))
                #     cv2.imshow("Layer "+str(l), cv2.resize(layerarray, dsize=(layerarray.shape[1]*5, layerarray.shape[0]*5), interpolation=cv2.INTER_AREA))

                cv2.waitKey(25)

            # Pause and reset controller if ESC key pressed once
            if km.is_pressed_once(km.ESC):
                pause = True
                bc.resetKeyState()

            # Pause loop
            while pause:
                if km.is_pressed_once(km.ESC) or not gd.isActive() or not gd.inGame():
                    pause = False

        else:
            gameInit = False
            bc.resetKeyState()
            cv2.destroyAllWindows()

if visualise:
    cv2.destroyAllWindows()
gd.stopAPI()
pygame.quit()
keylistener.stop()
