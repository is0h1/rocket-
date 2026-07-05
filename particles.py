from kivymd.app import MDApp
from kivymd.uix.floatlayout import MDFloatLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivy.uix.image import Image
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.screen import MDScreen
from random import randint
from kivy.clock import Clock
from kivy.graphics import Color
from kivy.animation import Animation
from kivy.metrics import dp


YELLOW_COLOR = (1, 1, 0, 0.7)
RED_COLOR = (1, 0, 0, 0.5)

LIFE_TIME_DEF = 3

DIRECTION_UP = 1
DIRECTION_DOWN = -1
SPEED_DEF = 100  # швидкість руху частинки в dp

class Particle(Image):
    def __init__(self, direction=DIRECTION_DOWN, life=LIFE_TIME_DEF, speed=SPEED_DEF, **kwargs):
        super().__init__(**kwargs)
        self.direction = direction
        self.life = life                     # скільки живе частинка
        self.speed = self.direction * dp(randint(int(speed * self.life / 2), int(speed * self.life)))   # рух вниз / вгору
        self.size_hint = (None, None)

        self.size_hint=(None, None)

        anim = Animation(color=YELLOW_COLOR, duration=self.life * 0.3) +\
               Animation(color=RED_COLOR, duration=self.life * 0.7, transition="out_quad")  #, transition='in_sine'

        #Зменшиння
        anim &= Animation(width=dp(20), duration=self.life)

        # Центрування частинки
        center_x = self.center_x
        anim &= Animation(center_x=center_x, duration=self.life)

        # Зміщення по Y
        anim &= Animation(y=self.y + self.speed, duration=self.life)

        anim.start(self)

        anim.on_complete = self.destroy

    def destroy(self, *args):
        if self.parent:
            self.parent.remove_widget(self)

class MainScreen(MDScreen):
    def on_kv_post(self, widget):
         Clock.schedule_interval(self.spawn_fire, 1 / 30)

    def spawn_fire(self, dt):
         # створюємо нову частинку
         p = Particle(
                source="assets/images/particle_simple.png",  # часточка вогню
                width=50 + randint(0, 50),
                center_x=self.center_x + randint(-10, 10),
                y=self.center_y + randint(-5, 5),
                life=2,
                speed=80,
                direction=DIRECTION_UP
        )
         self.add_widget(p)

         # if len(self.particles) > 1: print(self.particles[1].x)

class ParticlesApp(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Purple"

        self.sm = MDScreenManager()
        self.sm.add_widget(MainScreen(name='main'))
        return self.sm

if __name__ == "__main__":
    app = ParticlesApp()
    app.run()