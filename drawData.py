import GameDataAPI as gd
import pygame
import os

pygame.init()
START_RES = (500,500)
WHITE = (255,255,255)
curDir = os.path.dirname(os.path.realpath(__file__))
background = None
hasInit = False

''' Initialise for drawing stage '''
def init():
    global background, hasInit, window, stageRes
    # Window resolution is now the size of the cambounds
    stageRes = (gd.cambounds()["x1"], gd.cambounds()["y1"])
    window = pygame.display.set_mode(stageRes)
    # Now stuff has been initialised
    hasInit = True

'''Main driver code'''
if __name__ == "__main__":
    window = pygame.display.set_mode(START_RES)
    font = pygame.font.SysFont("Comic Sans", 50)
    gd.startAPI()

    while gd.isActive():
        window.fill(WHITE)  # Fills background colour

        if gd.inGame():
            gd.updateAPI()
            # Init stage
            if not hasInit:
                init()

            # Main update stage
            for t in gd.terrain():
                window.blit(t.img, t.pos)
            for p in gd.platforms():
                pygame.draw.rect(window, (255, 0, 255, 25), pygame.Rect(p["x"],p["y"],p["w"],p["h"]))
            pygame.draw.rect(window, (0, 0, 255, 25), pygame.Rect(gd.player.pos, gd.player.dim))
            pygame.draw.rect(window, (0, 0, 255, 25), pygame.Rect(gd.opponent.pos, gd.opponent.dim))
            window.blit(font.render(str(stageRes), True, (0,0,0)), (150,150))
        else:
            window.blit(font.render("Not In Game", True, (0,0,0)), (150,150))
            hasInit = False

        pygame.display.flip()   # Swap frame buffers and draw completed frame to display

gd.joinHandler()
pygame.quit()
