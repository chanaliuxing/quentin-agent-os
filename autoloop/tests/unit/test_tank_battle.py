import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add outputproduct to path
sys.path.append(os.path.join(os.getcwd(), 'outputproduct'))

@pytest.fixture
def mock_game():
    # Mock tkinter
    mock_tk = MagicMock()
    mock_canvas = MagicMock()
    
    # Patch tkinter before importing or using TankBattle
    with (patch('tkinter.Tk', return_value=mock_tk), 
          patch('tkinter.Canvas', return_value=mock_canvas)):
        from tank_battle import TankBattle
        # Prevent the game loop from starting automatically
        with patch.object(TankBattle, 'game_loop'):
            game = TankBattle(mock_tk)
            return game

def test_initial_state(mock_game):
    assert mock_game.player['health'] == 100
    assert len(mock_game.enemies) == 3
    assert mock_game.running == True

def test_check_collision_boundary(mock_game):
    # WIDTH=800, HEIGHT=600
    # Collision at boundary
    assert mock_game.check_collision(-1, 300, 30) == True
    assert mock_game.check_collision(801, 300, 30) == True
    assert mock_game.check_collision(400, -1, 30) == True
    assert mock_game.check_collision(400, 601, 30) == True
    
    # No collision in middle
    assert mock_game.check_collision(400, 300, 30) == False

def test_check_collision_walls(mock_game):
    # Walls: (200, 100, 50, 200), (500, 300, 200, 50), (100, 400, 150, 100)
    # Check collision with first wall (200, 100, 50, 200)
    assert mock_game.check_collision(225, 150, 30) == True
    
    # Check no collision near wall
    assert mock_game.check_collision(150, 150, 30) == False

def test_shoot(mock_game):
    initial_bullets = len(mock_game.bullets)
    mock_game.shoot(mock_game.player)
    assert len(mock_game.bullets) == initial_bullets + 1
    assert mock_game.bullets[-1]['owner'] == 'player'

def test_update_bullets_hit_enemy(mock_game):
    # Setup an enemy at a known position
    enemy = mock_game.enemies[0]
    enemy['x'] = 400
    enemy['y'] = 400
    enemy['health'] = 50
    
    # Create a bullet headed for the enemy
    mock_game.bullets = [{
        "x": 400,
        "y": 400,
        "angle": 0,
        "owner": "player"
    }]
    
    mock_game.update()
    
    # Bullet should have hit and been removed
    assert len(mock_game.bullets) == 0
    # Enemy health should have decreased
    assert enemy['health'] == 40

def test_update_bullets_hit_player(mock_game):
    mock_game.player['x'] = 100
    mock_game.player['y'] = 100
    mock_game.player['health'] = 100
    
    # Create a bullet headed for the player
    mock_game.bullets = [{
        "x": 100,
        "y": 100,
        "angle": 0,
        "owner": "enemy"
    }]
    
    mock_game.update()
    
    assert len(mock_game.bullets) == 0
    assert mock_game.player['health'] == 90

def test_game_over_condition(mock_game):
    mock_game.player['health'] = 0
    mock_game.update()
    assert mock_game.running == False
