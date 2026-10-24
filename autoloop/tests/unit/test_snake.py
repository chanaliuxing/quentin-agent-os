import pytest
import sys
import os

# Ensure src/junk is in the path so we can import snake
sys.path.append(os.path.join(os.getcwd(), 'src', 'junk'))

from snake import SnakeGame

def test_initialization():
    game = SnakeGame(20, 20)
    assert len(game.snake) == 3
    assert game.score == 0
    assert not game.game_over
    assert game.direction == 'RIGHT'

def test_move_right():
    game = SnakeGame(20, 20)
    head_before = list(game.snake[0])
    game.direction = 'RIGHT'
    game.step()
    head_after = list(game.snake[0])
    assert head_after[1] == head_before[1] + 1
    assert head_after[0] == head_before[0]

def test_move_up():
    game = SnakeGame(20, 20)
    head_before = list(game.snake[0])
    game.direction = 'UP'
    game.step()
    head_after = list(game.snake[0])
    assert head_after[0] == head_before[0] - 1
    assert head_after[1] == head_before[1]

def test_collision_wall():
    game = SnakeGame(10, 10)
    game.direction = 'RIGHT'
    # Move until wall collision
    for _ in range(10):
        if not game.step():
            break
    assert game.game_over

def test_eat_food():
    game = SnakeGame(20, 20)
    # Teleport snake to be right next to food
    game.snake = [[10, 10], [10, 9], [10, 8]]
    game.food = [10, 11]
    game.direction = 'RIGHT'
    game.step()
    assert game.score == 1
    assert len(game.snake) == 4 # Snake grew

def test_direction_change_opposites():
    game = SnakeGame(20, 20)
    game.direction = 'RIGHT'
    game.change_direction('LEFT') # Should NOT change
    assert game.direction == 'RIGHT'
    game.change_direction('UP') # Should change
    assert game.direction == 'UP'
    game.change_direction('DOWN') # Should NOT change
    assert game.direction == 'UP'

def test_self_collision():
    game = SnakeGame(20, 20)
    # Arrange snake in a circle to collide with itself
    game.snake = [[10, 10], [10, 11], [11, 11], [11, 10], [10, 10]]
    # This setup is already in collision but let's make it step into itself.
    game.snake = [[10, 10], [10, 11], [11, 11], [11, 10]]
    game.direction = 'UP'
    # Next step head will be [9, 10] - OK
    game.step()
    # Now head is [9, 10]. Snake is [[9,10], [10,10], [10,11], [11,11]]
    # Let's turn RIGHT
    game.direction = 'RIGHT'
    game.step()
    # Head is [9, 11]. Snake is [[9,11], [9,10], [10,10], [10,11]]
    # Let's turn DOWN
    game.direction = 'DOWN'
    game.step()
    # Head is [10, 11] which is already in snake body!
    assert not game.step()
    assert game.game_over
