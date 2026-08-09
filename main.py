from kivymd.app import MDApp
from kivymd.uix.widget import MDWidget
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.screen import MDScreen
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.window import Window
from kivy import platform
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle
from random import randint
from kivymd.uix.button import MDFlatButton
from kivymd.uix.dialog import MDDialog
from kivy.core.window import Keyboard
from kivy.properties import NumericProperty
from kivymd.uix.fitimage import FitImage
from particles import Particle
import math

FPS = 30
BULLET_SPEED = dp(600)
SHIP_SPEED = dp(300)
SHIP_SPEED_FORWARD = dp(180)
DIR_UP = 1
DIR_DOWN = -1

SPAWN_ENEMY_TIME = 2
HP_DEF = 3

FIRE_RATE_MIN = 0.5
FIRE_RATE_MEDIUM = 2

SPAWN_METEOR_TIME = 1.2
METEOR_SPEED_MIN = dp(150)
METEOR_SPEED_MAX = dp(320)
METEOR_SIZE_MIN = dp(40)
METEOR_SIZE_MAX = dp(90)

# ---- Бос ----
# Скільки секунд треба вижити, щоб з'явився бос (заповнення смуги вгорі).
BOSS_SURVIVE_TIME = 60
BOSS_HP = 3
# Наскільки боса "гойдає" по горизонталі, щоб він не стояв мертво.
BOSS_SWAY_SPEED = 1.4
BOSS_SWAY_RANGE = dp(70)

BOSS_ATTACKS_BEFORE_VULNERABLE = 2
BOSS_VULNERABLE_TIME = 5
BOSS_COOLDOWN_TIME = 1.0
BOSS_TELEGRAPH_TIME = 0.7

# Атака 1: залп куль по колу навсібіч.
BOSS_RADIAL_BULLET_COUNT = 20
BOSS_RADIAL_BULLET_SPEED = dp(240)
BOSS_RADIAL_ACTIVE_TIME = 0.4

# Атака 2: "червона стіна" з проміжком, яку треба облетіти.
BOSS_WALL_TELEGRAPH_TIME = 1.0
BOSS_WALL_ACTIVE_TIME = 1.2
BOSS_WALL_GAP_WIDTH = dp(140)
BOSS_WALL_HEIGHT = dp(40)

# Атака 3 (додав сам): 3 прицільні постріли по позиції гравця з невеликою
# затримкою між ними - змушує рухатись, а не стояти на місці.
BOSS_AIMED_TELEGRAPH_TIME = 0.6
BOSS_AIMED_SHOT_COUNT = 3
BOSS_AIMED_SHOT_INTERVAL = 0.3
BOSS_AIMED_SHOT_SPEED = dp(420)

# Невразливість гравця на мить після отримання шкоди від боса, щоб одна
# і та сама атака не знімала кілька hp за один кадр.
PLAYER_HIT_INVULN_TIME = 0.6

# Хітбокси (зона зіткнення) для корабля гравця і метеоритів навмисно
# менші за їх видиму картинку - так маневрувати між ними реальніше і
# приємніше, ніж коли зіштовхуєшся ще до візуального дотику.
PLAYER_HITBOX_SCALE = 0.55
METEOR_HITBOX_SCALE = 0.7


def _shrink_rect(widget, scale):
    """Повертає (x, y, w, h) прямокутник, стиснутий навколо центру віджета."""
    w = widget.width * scale
    h = widget.height * scale
    x = widget.center_x - w / 2
    y = widget.center_y - h / 2
    return x, y, w, h


def _rects_collide(rect_a, rect_b):
    ax, ay, aw, ah = rect_a
    bx, by, bw, bh = rect_b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def hitbox_collide(widget_a, scale_a, widget_b, scale_b):
    """Перевірка зіткнення двох віджетів з урахуванням масштабу хітбоксу
    (1.0 = звичайний collide_widget, менше значення = менша зона)."""
    return _rects_collide(
        _shrink_rect(widget_a, scale_a),
        _shrink_rect(widget_b, scale_b),
    )

KEYCODE_TO_KEY = {code: name for name, code in Keyboard.keycodes.items()}

KEY_ACTION_MAP = {
    'left': 'left',
    'right': 'right',
    'up': 'up',
    'down': 'down',
    'spacebar': 'shot',
}


class Shot(MDWidget):
    def __init__(self, direction, owner, **kwargs):
        super().__init__(**kwargs)
        self.direction = direction
        self.owner = owner


class Meteor(Image):
    """
    Метеорит - просто летить прямо вниз з випадковою швидкістю та
    розміром. Його неможна знищити пострілами (кулі просто пролітають
    крізь нього) - гравець повинен його облітати. Зіткнення з кораблем
    гравця = game over, як і зіткнення з ворожим кораблем.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.speed = randint(int(METEOR_SPEED_MIN), int(METEOR_SPEED_MAX))

    def update(self, dt):
        self.y -= self.speed * dt


class Boss(Image):
    """
    Бос: стоїть вгорі екрана (не летить на гравця), легко гойдається
    в боки для "живості". Має hp = BOSS_HP і атакує по колу з трьох
    видів атак. Отримує шкоду лише коли self.vulnerable == True.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.hp = BOSS_HP
        self.max_hp = BOSS_HP
        self.vulnerable = False
        self.base_center_x = 0
        self._sway_t = 0

    def update(self, dt):
        self._sway_t += dt * BOSS_SWAY_SPEED
        self.center_x = self.base_center_x + math.sin(self._sway_t) * BOSS_SWAY_RANGE


class BossBullet(MDWidget):
    """Куля боса, що летить у довільному напрямку (не тільки вертикально)."""

    def __init__(self, vx, vy, **kwargs):
        super().__init__(**kwargs)
        self.vx = vx
        self.vy = vy

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt


class RectHazard(Widget):
    """
    Простий кольоровий прямокутник для позначення небезпечної зони
    (використовується для попередження і самої атаки "стіна" боса).
    Малюється напряму через canvas, тому не потребує правила в .kv.
    """

    def __init__(self, color=(1, 0.15, 0.1, 0.9), **kwargs):
        kwargs.setdefault('size_hint', (None, None))
        super().__init__(**kwargs)
        with self.canvas:
            self._color = Color(*color)
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_rect, size=self._update_rect)

    def _update_rect(self, *args):
        self._rect.pos = self.pos
        self._rect.size = self.size


class Ship(Image):
    hp = NumericProperty()
    max_hp = NumericProperty()

    def __init__(self, direction: int = DIR_UP, hp: int = HP_DEF,
                 fire_rate: int = FIRE_RATE_MEDIUM, **kwargs):
        super().__init__(**kwargs)
        self.direction = direction
        self.hp = self.max_hp = hp
        self.fire_rate = fire_rate
        self._last_shot = self.fire_rate
        self.anim_delay = 1 / 30
        self._lastAnim = self.anim_delay

    def moveLeft(self, dt):
        self.pos[0] -= SHIP_SPEED * dt

    def moveRight(self, dt):
        self.pos[0] += SHIP_SPEED * dt

    def moveUp(self, dt):
        self.pos[1] += SHIP_SPEED * dt

    def moveDown(self, dt):
        self.pos[1] -= SHIP_SPEED * dt

    def shot(self):
        shot = Shot(self.direction, owner=self)
        shot.center_x = self.center_x
        shot.y = self.top if self.direction == DIR_UP else self.y - shot.height

        game_screen = MDApp.get_running_app().sm.get_screen('game')
        game_screen.bullets.append(shot)
        self.parent.add_widget(shot)

        self._last_shot = 0

    def update(self, dt):
        self._last_shot += dt
        self.animation(dt)

    def animation(self, dt):
        pass


class PlayerShip(Ship):
    def __init__(self, **kwargs):
        super().__init__(direction=DIR_UP, fire_rate=FIRE_RATE_MIN, **kwargs)

    def update(self, dt, keys):
        super().update(dt)

        for key in keys:
            if keys[key]:
                if key == 'left' and self.x > 0:
                    self.moveLeft(dt)
                if key == 'right' and self.right < Window.width:
                    self.moveRight(dt)
                if key == 'up' and self.top < Window.height:
                    self.moveUp(dt)
                if key == 'down' and self.y > 0:
                    self.moveDown(dt)
                if key == 'shot':
                    if self._last_shot >= self.fire_rate:
                        self.shot()
                keys[key] = False

    def animation(self, dt):
        if self._lastAnim >= self.anim_delay:
            p = Particle(
                source="assets/images/particle_real.png",
                width=dp(50 + randint(0, 50)),
                center_x=dp(self.center_x + randint(-15, 15)),
                y=dp(self.y + randint(-5, 0)),
                life=0.3,
                speed=0,
                direction=self.direction * -1,
                opacity=1
            )
            if self.parent:
                self.parent.add_widget(p)
            self._lastAnim = 0
        self._lastAnim += dt


class EnemyShip(Ship):
    def __init__(self, **kwargs):
        super().__init__(direction=DIR_DOWN, **kwargs)

    def update(self, dt):
        super().update(dt)
        self.y -= SHIP_SPEED_FORWARD * dt
        if self._last_shot >= self.fire_rate:
            self.shot()

    def animation(self, dt):
        if self._lastAnim >= self.anim_delay:
            p = Particle(
                source="assets/images/particle_real.png",
                width=dp(50 + randint(0, 50)),
                center_x=dp(self.center_x + randint(-15, 15)),
                y=dp(self.center_y + randint(-5, 0)),
                life=0.3,
                speed=0,
                direction=self.direction * -1,
                opacity=1
            )
            if self.parent:
                self.parent.add_widget(p)
            self._lastAnim = 0
        self._lastAnim += dt


class GameScreen(MDScreen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.eventkeys = {}
        self.ship = None
        self.enemyShips = []
        self.bullets = []
        self.meteors = []
        self.pauseMenu = None

        self.spawn_delay = SPAWN_ENEMY_TIME
        self.time_last_spawn = 0

        self.meteor_spawn_delay = SPAWN_METEOR_TIME
        self.time_last_meteor_spawn = 0

        # ---- стан боса ----
        self.boss = None
        self.boss_bullets = []
        self.boss_state = None
        self.boss_state_timer = 0
        self.boss_state_duration = 0
        self.boss_attacks_done = 0
        self.boss_attack_cycle = ['radial', 'wall', 'aimed']
        self.boss_attack_index = 0
        self.boss_time_survived = 0
        self.boss_defeated = False
        self.ship_invuln_timer = 0
        self.boss_aimed_shots_fired = 0
        self.boss_wall_gap_x = 0
        self.boss_wall_telegraph_widget = None
        self.boss_wall_active_widget = None

        Window.bind(on_key_down=self._on_key_down)
        Window.bind(on_key_up=self._on_key_up)

    def on_enter(self, *args):
        self.updateEvent = Clock.schedule_interval(self.update, 1 / FPS)
        self.ship = self.ids.ship
        self.ship.hp = self.ship.max_hp
        # Задаємо стартову позицію по X один раз тут (а не через pos_hint
        # в kv), інакше FloatLayout буде постійно "стягувати" корабель
        # назад до центру при кожному додаванні/видаленні дочірнього
        # віджета (кулі, частинки анімації двигуна тощо).
        self.ship.center_x = Window.width / 2

        # Повне скидання стану на випадок повторної гри ("PLAY AGAIN") -
        # той самий екземпляр GameScreen перевикористовується, тому просто
        # чистимо всі списки й таймери заново.
        self.enemyShips = []
        self.bullets = []
        self.meteors = []
        self.spawn_delay = SPAWN_ENEMY_TIME
        self.time_last_spawn = 0
        self.meteor_spawn_delay = SPAWN_METEOR_TIME
        self.time_last_meteor_spawn = 0

        self.boss = None
        self.boss_bullets = []
        self.boss_state = None
        self.boss_state_timer = 0
        self.boss_attacks_done = 0
        self.boss_attack_index = 0
        self.boss_time_survived = 0
        self.boss_defeated = False
        self.ship_invuln_timer = 0
        self.boss_wall_telegraph_widget = None
        self.boss_wall_active_widget = None
        self.ids.boss_meter.value = 0
        self.ids.boss_hint_label.text = ""
        self.ids.boss_hint_label.opacity = 0

        return super().on_enter(*args)

    def spawn_enemy(self):
        enemy = EnemyShip()
        enemy.pos = (randint(0, int(Window.width - enemy.width)), Window.height)
        self.enemyShips.append(enemy)
        self.ids.front.add_widget(enemy)

    def spawn_meteor(self):
        size = randint(int(METEOR_SIZE_MIN), int(METEOR_SIZE_MAX))
        meteor = Meteor(source="assets/images/meteor.png", size_hint=(None, None), size=(size, size))
        meteor.pos = (randint(0, int(Window.width - meteor.width)), Window.height)
        self.meteors.append(meteor)
        self.ids.front.add_widget(meteor)

    def spawn_boss(self):
        # Очищаємо поле від звичайних ворогів/метеоритів/куль, щоб бій з
        # босом був чесним і читабельним (не накладався на звичайний спавн).
        for enemy in self.enemyShips[:]:
            self.enemyShips.remove(enemy)
            self.ids.front.remove_widget(enemy)
        for meteor in self.meteors[:]:
            self.meteors.remove(meteor)
            self.ids.front.remove_widget(meteor)
        for bullet in self.bullets[:]:
            if bullet.owner != self.ship:
                self.remove_bullet(bullet)

        boss = Boss(source="assets/images/boss_ships.png")
        boss.pos = ((Window.width - boss.width) / 2, Window.height - boss.height - dp(30))
        boss.base_center_x = boss.center_x
        boss.opacity = 0
        self.boss = boss
        self.ids.front.add_widget(boss)
        self.boss_enter_state('appear', 1.0)

    def update(self, dt):
        self.ship.update(dt, self.eventkeys)

        if self.ship_invuln_timer > 0:
            self.ship_invuln_timer -= dt

        # Поки боса немає (і ще не переміг) - звичайний спавн ворогів і
        # метеоритів, і накопичуємо прогрес до появи боса.
        if self.boss is None and not self.boss_defeated:
            self.time_last_spawn += dt
            if self.time_last_spawn >= self.spawn_delay:
                self.spawn_enemy()
                self.time_last_spawn = 0

            self.time_last_meteor_spawn += dt
            if self.time_last_meteor_spawn >= self.meteor_spawn_delay:
                self.spawn_meteor()
                self.time_last_meteor_spawn = 0

            self.boss_time_survived += dt
            progress = min(self.boss_time_survived / BOSS_SURVIVE_TIME, 1.0)
            self.ids.boss_meter.value = progress * 100
            if self.boss_time_survived >= BOSS_SURVIVE_TIME:
                self.spawn_boss()
        elif self.boss is not None:
            self.update_boss(dt)

        for ship in self.enemyShips[:]:
            ship.update(dt)
            if ship.top < 0:
                self.enemyShips.remove(ship)
                self.ids.front.remove_widget(ship)
                continue

            if hitbox_collide(ship, 1.0, self.ship, PLAYER_HITBOX_SCALE):
                self.game_over()

        for meteor in self.meteors[:]:
            meteor.update(dt)
            if meteor.top < 0:
                self.meteors.remove(meteor)
                self.ids.front.remove_widget(meteor)
                continue

            if hitbox_collide(meteor, METEOR_HITBOX_SCALE, self.ship, PLAYER_HITBOX_SCALE):
                self.game_over()

        self.manage_bullets(dt)

    # ==================== БОС ====================

    def boss_enter_state(self, state, duration):
        self.boss_state = state
        self.boss_state_duration = duration
        self.boss_state_timer = duration

    def update_boss(self, dt):
        boss = self.boss
        boss.update(dt)

        # Плавна поява боса (зростання прозорості) під час стану 'appear'.
        if self.boss_state == 'appear':
            boss.opacity = 1 - max(self.boss_state_timer, 0) / self.boss_state_duration
        else:
            boss.opacity = 1

        # Рух і колізії куль боса.
        for b in self.boss_bullets[:]:
            b.update(dt)
            if (b.right < 0 or b.x > Window.width
                    or b.top < 0 or b.y > Window.height):
                self.boss_bullets.remove(b)
                self.ids.front.remove_widget(b)
                continue
            if self.ship_invuln_timer <= 0 and hitbox_collide(b, 1.0, self.ship, PLAYER_HITBOX_SCALE):
                self.boss_bullets.remove(b)
                self.ids.front.remove_widget(b)
                self.damage_player()

        # Смуга вгорі під час бою показує hp боса.
        self.ids.boss_meter.value = (boss.hp / BOSS_HP) * 100

        # Атака "прицільні постріли" стріляє з інтервалом протягом активної фази.
        if self.boss_state == 'aimed_active':
            elapsed = self.boss_state_duration - self.boss_state_timer
            if (self.boss_aimed_shots_fired < BOSS_AIMED_SHOT_COUNT
                    and elapsed >= self.boss_aimed_shots_fired * BOSS_AIMED_SHOT_INTERVAL):
                self.fire_boss_aimed_shot()

        self.boss_state_timer -= dt
        if self.boss_state_timer <= 0:
            self.boss_advance_state()

    def boss_advance_state(self):
        finished = self.boss_state

        if finished == 'appear':
            self.boss_enter_state('cooldown', BOSS_COOLDOWN_TIME)

        elif finished == 'cooldown':
            self.start_next_boss_attack()

        elif finished == 'radial_telegraph':
            self.fire_boss_radial_burst()
            self.boss_enter_state('radial_active', BOSS_RADIAL_ACTIVE_TIME)

        elif finished == 'wall_telegraph':
            self.activate_boss_wall()
            self.boss_enter_state('wall_active', BOSS_WALL_ACTIVE_TIME)

        elif finished == 'aimed_telegraph':
            self.boss_aimed_shots_fired = 0
            duration = BOSS_AIMED_SHOT_INTERVAL * BOSS_AIMED_SHOT_COUNT + 0.2
            self.boss_enter_state('aimed_active', duration)

        elif finished in ('radial_active', 'wall_active', 'aimed_active'):
            self.finish_boss_attack()

        elif finished == 'vulnerable':
            self.boss.vulnerable = False
            self.ids.boss_hint_label.text = ""
            self.ids.boss_hint_label.opacity = 0
            self.boss_attacks_done = 0
            self.boss_enter_state('cooldown', BOSS_COOLDOWN_TIME)

    def start_next_boss_attack(self):
        attack = self.boss_attack_cycle[self.boss_attack_index % len(self.boss_attack_cycle)]
        self.boss_attack_index += 1

        if attack == 'radial':
            self.boss_enter_state('radial_telegraph', BOSS_TELEGRAPH_TIME)
        elif attack == 'wall':
            self.prepare_boss_wall_telegraph()
            self.boss_enter_state('wall_telegraph', BOSS_WALL_TELEGRAPH_TIME)
        elif attack == 'aimed':
            self.boss_enter_state('aimed_telegraph', BOSS_AIMED_TELEGRAPH_TIME)

    def finish_boss_attack(self):
        self.clear_boss_wall_widgets()
        self.boss_attacks_done += 1

        if self.boss_attacks_done >= BOSS_ATTACKS_BEFORE_VULNERABLE:
            self.boss_attacks_done = 0
            self.boss.vulnerable = True
            self.ids.boss_hint_label.text = "БИЙ БОСА!"
            self.ids.boss_hint_label.opacity = 1
            self.boss_enter_state('vulnerable', BOSS_VULNERABLE_TIME)
        else:
            self.boss_enter_state('cooldown', BOSS_COOLDOWN_TIME)

    def fire_boss_radial_burst(self):
        boss = self.boss
        for i in range(BOSS_RADIAL_BULLET_COUNT):
            angle = (2 * math.pi / BOSS_RADIAL_BULLET_COUNT) * i
            vx = math.cos(angle) * BOSS_RADIAL_BULLET_SPEED
            vy = math.sin(angle) * BOSS_RADIAL_BULLET_SPEED
            bullet = BossBullet(vx=vx, vy=vy)
            bullet.center = boss.center
            self.boss_bullets.append(bullet)
            self.ids.front.add_widget(bullet)

    def prepare_boss_wall_telegraph(self):
        gap_x = randint(0, max(0, int(Window.width - BOSS_WALL_GAP_WIDTH)))
        self.boss_wall_gap_x = gap_x
        wall_y = self.boss.y - BOSS_WALL_HEIGHT - dp(10)

        left_width = gap_x
        right_x = gap_x + BOSS_WALL_GAP_WIDTH
        right_width = Window.width - right_x

        widgets = []
        if left_width > 0:
            widgets.append(RectHazard(
                color=(1, 0.15, 0.1, 0.35),
                pos=(0, wall_y), size=(left_width, BOSS_WALL_HEIGHT),
            ))
        if right_width > 0:
            widgets.append(RectHazard(
                color=(1, 0.15, 0.1, 0.35),
                pos=(right_x, wall_y), size=(right_width, BOSS_WALL_HEIGHT),
            ))

        for w in widgets:
            self.ids.front.add_widget(w)
        self.boss_wall_telegraph_widget = widgets

    def activate_boss_wall(self):
        self.clear_boss_wall_widgets(only_telegraph=True)

        gap_x = self.boss_wall_gap_x
        wall_y = self.boss.y - BOSS_WALL_HEIGHT - dp(10)
        left_width = gap_x
        right_x = gap_x + BOSS_WALL_GAP_WIDTH
        right_width = Window.width - right_x

        widgets = []
        if left_width > 0:
            widgets.append(RectHazard(
                color=(1, 0.1, 0.05, 0.9),
                pos=(0, wall_y), size=(left_width, BOSS_WALL_HEIGHT),
            ))
        if right_width > 0:
            widgets.append(RectHazard(
                color=(1, 0.1, 0.05, 0.9),
                pos=(right_x, wall_y), size=(right_width, BOSS_WALL_HEIGHT),
            ))

        for w in widgets:
            self.ids.front.add_widget(w)
        self.boss_wall_active_widget = widgets

        # Разова перевірка в момент активації: гравець або в безпечному
        # проміжку, або отримує влучання.
        in_gap = gap_x <= self.ship.center_x <= gap_x + BOSS_WALL_GAP_WIDTH
        if not in_gap and self.ship_invuln_timer <= 0:
            self.damage_player()

    def clear_boss_wall_widgets(self, only_telegraph=False):
        if self.boss_wall_telegraph_widget:
            for w in self.boss_wall_telegraph_widget:
                if w.parent:
                    self.ids.front.remove_widget(w)
            self.boss_wall_telegraph_widget = None
        if not only_telegraph and self.boss_wall_active_widget:
            for w in self.boss_wall_active_widget:
                if w.parent:
                    self.ids.front.remove_widget(w)
            self.boss_wall_active_widget = None

    def fire_boss_aimed_shot(self):
        boss = self.boss
        dx = self.ship.center_x - boss.center_x
        dy = self.ship.center_y - boss.center_y
        dist = max(1, math.hypot(dx, dy))
        vx = dx / dist * BOSS_AIMED_SHOT_SPEED
        vy = dy / dist * BOSS_AIMED_SHOT_SPEED

        bullet = BossBullet(vx=vx, vy=vy)
        bullet.center = boss.center
        self.boss_bullets.append(bullet)
        self.ids.front.add_widget(bullet)
        self.boss_aimed_shots_fired += 1

    def damage_player(self):
        self.ship.hp -= 1
        self.ship_invuln_timer = PLAYER_HIT_INVULN_TIME
        if self.ship.hp <= 0:
            self.game_over()

    def boss_win(self):
        self.boss_defeated = True
        self.updateEvent.cancel()

        for enemy in self.enemyShips[:]:
            self.enemyShips.remove(enemy)
            self.ids.front.remove_widget(enemy)
        for bullet in self.bullets[:]:
            self.ids.front.remove_widget(bullet)
            self.bullets.remove(bullet)
        for meteor in self.meteors[:]:
            self.ids.front.remove_widget(meteor)
            self.meteors.remove(meteor)
        for b in self.boss_bullets[:]:
            self.ids.front.remove_widget(b)
            self.boss_bullets.remove(b)
        self.clear_boss_wall_widgets()
        if self.boss and self.boss.parent:
            self.ids.front.remove_widget(self.boss)
        self.boss = None

        self.manager.current = 'victory'

    def manage_bullets(self, dt):
        for bullet in self.bullets[:]:
            bullet.y += BULLET_SPEED * dt * bullet.direction
            self.check_collisions(bullet)
            if bullet in self.bullets and (bullet.top < 0 or bullet.y > Window.height):
                self.remove_bullet(bullet)

    def check_collisions(self, bullet):
        if bullet.owner == self.ship:
            for enemy in self.enemyShips[:]:
                if bullet.collide_widget(enemy):
                    enemy.hp -= 1
                    if enemy.hp <= 0:
                        self.enemyShips.remove(enemy)
                        self.ids.front.remove_widget(enemy)
                    self.remove_bullet(bullet)
                    return

            if self.boss and self.boss.vulnerable and bullet.collide_widget(self.boss):
                self.boss.hp -= 1
                self.remove_bullet(bullet)
                if self.boss.hp <= 0:
                    self.boss_win()
        else:
            if hitbox_collide(bullet, 1.0, self.ship, PLAYER_HITBOX_SCALE):
                self.ship.hp -= 1
                if self.ship.hp <= 0:
                    self.game_over()
                self.remove_bullet(bullet)

    def remove_bullet(self, bullet):
        if bullet in self.bullets:
            self.bullets.remove(bullet)
        if bullet.parent:
            self.ids.front.remove_widget(bullet)

    def game_over(self):
        self.updateEvent.cancel()
        for enemy in self.enemyShips[:]:
            self.enemyShips.remove(enemy)
            self.ids.front.remove_widget(enemy)
        for bullet in self.bullets[:]:
            self.ids.front.remove_widget(bullet)
            self.bullets.remove(bullet)
        for meteor in self.meteors[:]:
            self.ids.front.remove_widget(meteor)
            self.meteors.remove(meteor)
        for b in self.boss_bullets[:]:
            self.ids.front.remove_widget(b)
            self.boss_bullets.remove(b)
        self.clear_boss_wall_widgets()
        if self.boss and self.boss.parent:
            self.ids.front.remove_widget(self.boss)
        self.boss = None

        self.manager.current = 'game_over'

    def pressKey(self, key):
        self.eventkeys[key] = True

    def releaseKey(self, key):
        self.eventkeys[key] = False

    def show_menu(self):
        self.updateEvent.cancel()
        if not self.pauseMenu:
            self.pauseMenu = MDDialog(
                title="Game Paused",
                text="Resume the game?",
                on_dismiss=self.resumeGame,
                buttons=[
                    MDFlatButton(
                        text="RESUME",
                        theme_text_color="Custom",
                        text_color=MDApp.get_running_app().theme_cls.primary_color,
                        on_press=self.pauseStop
                    )
                ],
            )
        self.pauseMenu.open()

    def pauseStop(self, *args):
        self.pauseMenu.dismiss()

    def resumeGame(self, *args):
        self.updateEvent = Clock.schedule_interval(self.update, 1 / FPS)

    def _on_key_down(self, window, keycode, *args, **kwargs):
        raw_key = KEYCODE_TO_KEY.get(keycode)
        action = KEY_ACTION_MAP.get(raw_key)
        if action is None:
            return
        self.eventkeys[action] = True

    def _on_key_up(self, window, keycode, *args, **kwargs):
        raw_key = KEYCODE_TO_KEY.get(keycode)
        action = KEY_ACTION_MAP.get(raw_key)
        if action is None:
            return
        self.eventkeys[action] = False


class GameOverScreen(MDScreen):
    pass


class VictoryScreen(MDScreen):
    pass


class MainScreen(MDScreen):
    pass


class ShooterApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Purple"

        self.sm = MDScreenManager()
        self.sm.add_widget(MainScreen(name='main'))
        self.sm.add_widget(GameScreen(name='game'))
        self.sm.add_widget(GameOverScreen(name='game_over'))
        self.sm.add_widget(VictoryScreen(name='victory'))

        return self.sm


if platform != 'android':
    Window.size = (450, 900)
    Window.top = 100
    Window.left = 600

app = ShooterApp()
app.run()
