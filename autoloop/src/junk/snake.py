import curses
import random
import time

class SnakeGame:
    def __init__(self, height, width):
        self.height = height
        self.width = width
        # Head is first element
        self.snake = [
            [height // 2, width // 4],
            [height // 2, width // 4 - 1],
            [height // 2, width // 4 - 2]
        ]
        self.food = self._generate_food()
        self.direction = 'RIGHT'
        self.score = 0
        self.game_over = False
        self.last_tail = None

    def _generate_food(self):
        while True:
            food = [random.randint(1, self.height - 2), random.randint(1, self.width - 2)]
            if food not in self.snake:
                return food

    def change_direction(self, new_direction):
        opposites = {
            'UP': 'DOWN',
            'DOWN': 'UP',
            'LEFT': 'RIGHT',
            'RIGHT': 'LEFT'
        }
        if new_direction != opposites.get(self.direction):
            self.direction = new_direction

    def step(self):
        if self.game_over:
            return False

        # Calculate new head
        head = list(self.snake[0])
        if self.direction == 'UP':
            head[0] -= 1
        elif self.direction == 'DOWN':
            head[0] += 1
        elif self.direction == 'LEFT':
            head[1] -= 1
        elif self.direction == 'RIGHT':
            head[1] += 1

        # Check for collisions with walls
        if (head[0] <= 0 or head[0] >= self.height - 1 or
            head[1] <= 0 or head[1] >= self.width - 1):
            self.game_over = True
            return False

        # Check for collisions with self
        if head in self.snake:
            self.game_over = True
            return False

        self.snake.insert(0, head)

        # Check for food
        if head == self.food:
            self.score += 1
            self.food = self._generate_food()
            self.last_tail = None # No tail to remove
        else:
            self.last_tail = self.snake.pop()
        
        return True

def main(stdscr):
    # Setup curses
    curses.curs_set(0)
    curses.noecho()
    sh, sw = stdscr.getmaxyx()
    game = SnakeGame(sh, sw)
    
    w = curses.newwin(sh, sw, 0, 0)
    w.keypad(1)
    w.timeout(100)

    # Initial instructions
    instr = "Arrows/WASD to move, ESC to quit"
    w.addstr(0, (sw - len(instr)) // 2, instr)

    # Drawing initial food
    w.addch(game.food[0], game.food[1], curses.ACS_PI)

    while not game.game_over:
        key = w.getch()
        
        # Mapping for inputs
        dirs = {
            curses.KEY_UP: 'UP', ord('w'): 'UP', ord('W'): 'UP',
            curses.KEY_DOWN: 'DOWN', ord('s'): 'DOWN', ord('S'): 'DOWN',
            curses.KEY_LEFT: 'LEFT', ord('a'): 'LEFT', ord('A'): 'LEFT',
            curses.KEY_RIGHT: 'RIGHT', ord('d'): 'RIGHT', ord('D'): 'RIGHT'
        }
        
        if key == curses.KEY_RESIZE:
            # Simple handling for resize: game over if it shrinks too much
            n_sh, n_sw = stdscr.getmaxyx()
            if n_sh < 10 or n_sw < 20:
                game.game_over = True
            continue
        
        if key in dirs:
            game.change_direction(dirs[key])
        elif key == 27: # ESC
            break

        if not game.step():
            break

        # Render: add head
        try:
            w.addch(game.snake[0][0], game.snake[0][1], curses.ACS_CKBOARD)
            # Clear tail
            if game.last_tail:
                w.addch(game.last_tail[0], game.last_tail[1], ' ')
            # Add food (it might have moved/been recreated)
            w.addch(game.food[0], game.food[1], curses.ACS_PI)
        except curses.error:
            # Handle possible window edge issues during resize
            pass

    # Game Over screen
    w.clear()
    msg = f"GAME OVER! SCORE: {game.score}"
    w.addstr(sh // 2, (sw - len(msg)) // 2, msg, curses.A_BOLD)
    retry_msg = "Press any key to exit"
    w.addstr(sh // 2 + 1, (sw - len(retry_msg)) // 2, retry_msg)
    w.nodelay(0)
    w.getch()

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
