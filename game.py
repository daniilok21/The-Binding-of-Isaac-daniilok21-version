import os
import sys
import random
from pprint import pprint
import time
import pygame
from threading import Thread
import math
import sqlite3


color = {'lobby': (0, 204, 102),
         'water': (79, 164, 184),
         'black': (0, 0, 0),
         'land': (97, 85, 79)}

ind = 'lobby'
use_magic = 'WaterBalloon'

# Изображение не получится загрузить
# без предварительной инициализации pygame
pygame.init()
size = width, height = 900, 600
screen = pygame.display.set_mode(size)
clock = pygame.time.Clock()

all_sprites = pygame.sprite.Group() # группа для всех спрайтов
person_sprite = pygame.sprite.Group() # группа главного персонажа
shop_menu_sprites = pygame.sprite.Group() # меню магазина
crosshair_sprites = pygame.sprite.Group() # группа курсора
hud_sprites = pygame.sprite.Group() # группа hud
enemy_sprites = pygame.sprite.Group() # группа врагов
camera_sprites = pygame.sprite.Group() # для камеры (передвижение объектов в зависимости от положения камеры)
walls_sprites = pygame.sprite.Group() # группа стен
doors_sprites = pygame.sprite.Group() # группа дверей
lvl_sprites = pygame.sprite.Group() # спрайты лвла
item_sprites = pygame.sprite.Group() # спрайты - предметы магазина

person_in_portal = False
person_in_end_game = False


def data_base():
    global health, health_max, protect, protect_max, mana, mana_max, money, can_casting, magic_using
    # Подключение к БД
    con = sqlite3.connect("database.sqlite")
    cur = con.cursor()

    result = cur.execute("""SELECT * FROM settings""").fetchall()
    for elem in result:
        print(elem)

    health, health_max = int(result[0][1]), result[0][2]
    protect, protect_max = int(result[1][1]), result[1][2]
    mana, mana_max = int(result[2][1]), result[2][2]
    money = int(result[3][1])
    magic_using = result[4][1]

    result = cur.execute("""SELECT name FROM magic WHERE get=1""").fetchall()
    can_casting = []
    for elem in result:
        can_casting.append(elem[0])
    con.close()
    print(can_casting)

image_cache = {}

def load_image(name, colorkey=None):
    if name in image_cache:
        return image_cache[name]
    fullname = os.path.join('data', name)
    if not os.path.isfile(fullname):
        print(f"Файл с изображением '{fullname}' не найден")
        sys.exit()
    image = pygame.image.load(fullname)
    if colorkey is not None:
        image = image.convert()
        if colorkey == -1:
            colorkey = image.get_at((0, 0))
        image.set_colorkey(colorkey)
    else:
        image = image.convert_alpha()
    image_cache[name] = image
    return image


def draw_text(surface, text, pos, font, color, outline_color, outline_width=2):
    # Рендерим текст с обводкой
    text_surface = font.render(text, True, color)
    outline_surface = font.render(text, True, outline_color)

    # Получаем прямоугольники для текстов
    text_rect = text_surface.get_rect(center=pos)
    outline_rect = outline_surface.get_rect(center=pos)

    # Рисуем обводку и текст
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:  # Не рисуем в центре
                surface.blit(outline_surface, outline_rect.move(dx, dy))
    surface.blit(text_surface, text_rect)


def clear_other_sprites():
    global person_in_portal
    Portal.person_in_portal = True
    for sprite in all_sprites:
        sprite.kill()
    for sprite in camera_sprites:
        sprite.kill()
    for sprite in crosshair_sprites:
        sprite.kill()
    person_in_portal = True


class MainMenu(pygame.sprite.Sprite):
    def __init__(self, group):
        super().__init__(group)
        self.image = load_image("main_menu.png", pygame.Color(0, 0, 0))
        self.rect = self.image.get_rect()


class Button(pygame.sprite.Sprite):
    def __init__(self, group):
        super().__init__(group)
        self.image = load_image("button.png")
        self.original_image = self.image
        self.scaled_image = pygame.transform.scale(self.original_image,
                                                   (int(self.original_image.get_width() / 3.8),
                                                    int(self.original_image.get_height() / 4)))
        self.image = self.scaled_image
        self.rect = self.image.get_rect()
        self.rect = self.rect.move(int(width / 2 - self.image.get_width() / 2), int(height / 5 + 125))
        self.is_active = True  # Флаг для отслеживания активности кнопки

    def update(self, *args):
        if self.is_active and args and args[0].type == pygame.MOUSEBUTTONDOWN and \
                self.rect.collidepoint(args[0].pos):
            start_game()
            self.is_active = False  # Деактивируем кнопку после нажатия
            self.kill()
        font = pygame.font.Font(None, 39)
        draw_text(screen, 'Play', (width / 2, height / 4 + 20 + 125), font, 'white', 'black')


class Ground(pygame.sprite.Sprite):
    def __init__(self, group, image):
        # НЕОБХОДИМО вызвать конструктор родительского класса Sprite.
        # Это очень важно !!!
        super().__init__(group)
        self.image = image
        self.rect = self.image.get_rect()


class Shop(pygame.sprite.Sprite):
    def __init__(self, group):
        super().__init__(group)
        self.image = load_image("shop.png", pygame.Color(0, 0, 0))
        self.rect = self.image.get_rect(topleft=(width / 3 * 2, height / 2))
        self.mask = pygame.mask.from_surface(self.image)


class Portal(pygame.sprite.Sprite):
    def __init__(self, group, sheet, x, columns=10, rows=1, y=None):
        super().__init__(group)
        self.frames = []
        self.cur_frame = 0
        self.frame_duration = 70
        self.y = y
        self.last_update = pygame.time.get_ticks()
        self.cut_sheet(sheet, columns, rows, self.frames)

        # Увеличение размера портала
        scale_factor = 3  # Увеличиваем в 2 раза
        self.frames = [pygame.transform.scale(frame, (frame.get_width() * scale_factor,
                                                      frame.get_height() * scale_factor)) for frame in self.frames]

        self.image = self.frames[self.cur_frame]
        if y != None:
            self.rect = self.image.get_rect(center=(x, y))
        else:
            self.rect = self.image.get_rect(center=(x, height // 8))

        self.mask = pygame.mask.from_surface(self.image)

    def cut_sheet(self, sheet, columns, rows, frames):
        self.rect = pygame.Rect(0, 0, sheet.get_width() // columns,
                                sheet.get_height() // rows)
        for j in range(rows):
            for i in range(columns):
                frame_location = (self.rect.w * i, self.rect.h * j)
                frames.append(sheet.subsurface(pygame.Rect(
                    frame_location, self.rect.size)))

    def animate(self):
        self.last_update = current_time
        self.cur_frame = (self.cur_frame + 1) % len(self.frames)
        self.image = self.frames[self.cur_frame]


class BluePortal(Portal):
    def __init__(self, group, sheet, x, columns=10, rows=1, y=None, need_information=None):
        super().__init__(group, sheet, x, columns, rows, y)
        self.pos_boss = y
        self.need_information = need_information

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.animate()
        if pygame.sprite.collide_mask(self, person) and self.y == None:
            clear_other_sprites()
            global lvl
            lvl = Lvl(camera_sprites, load_image('water_bg.png'), 'water', 3200, 640)
        elif pygame.sprite.collide_mask(self, person) and self.y != None:
            # время фраги заработок
            EndGame('win', self.need_information[0], self.need_information[1], self.need_information[2])


class GreenPortal(Portal):
    def __init__(self, group, sheet, x, columns=10, rows=1, y=None, need_information=None):
        super().__init__(group, sheet, x, columns, rows, y)
        self.pos_boss = y
        self.need_information = need_information

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.animate()
        if pygame.sprite.collide_mask(self, person) and self.y == None:
            clear_other_sprites()
            global lvl
            lvl = Lvl(camera_sprites, load_image('land_bg.png'), 'land', 1216, 896)
        elif pygame.sprite.collide_mask(self, person) and self.y != None:
            # время фраги заработок
            EndGame('win', self.need_information[0], self.need_information[1], self.need_information[2])


class RedPortal(Portal):
    def __init__(self, group, sheet, x, columns=10, rows=1):
        super().__init__(group, sheet, x, columns, rows)

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.animate()
        if pygame.sprite.collide_mask(self, person):
            clear_other_sprites()
            print('Огненный портал')


class DarkPortal(Portal):
    def __init__(self, group, sheet, x, columns=10, rows=1):
        super().__init__(group, sheet, x, columns, rows)

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.animate()
        if pygame.sprite.collide_mask(self, person):
            clear_other_sprites()
            print('Темный портал')


class LightPortal(Portal):
    def __init__(self, group, sheet, x, columns=10, rows=1):
        super().__init__(group, sheet, x, columns, rows)

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.animate()
        if pygame.sprite.collide_mask(self, person):
            clear_other_sprites()
            print('Светлый портал')


class Camera(pygame.sprite.Group):
    def __init__(self, group, lvl):
        global person, hud, crosshair, camera
        super().__init__(group)
        self.lvl = lvl
        self.display_surface = pygame.display.get_surface()
        self.offset = pygame.math.Vector2()
        self.half_w = self.display_surface.get_width() // 2
        self.half_h = self.display_surface.get_height() // 2
        self.ground_rect = lvl.image.get_rect(topleft=(0, 0))

        person = Person(load_image('person_idle.png'), load_image('person_walk.png'), camera=True)
        if not person.hud_visible:
            hud = Hud(camera_sprites)
        crosshair = Crosshair(camera_sprites)

    def center_target_camera(self, target):
        self.offset.x = target.rect.centerx - self.half_w
        self.offset.y = target.rect.centery - self.half_h

    def custom_draw(self, player):
        self.lvl.update()
        self.player = player
        # Вызов с основного цикла
        self.center_target_camera(player)
        ground_offset = self.ground_rect.topleft - self.offset
        self.display_surface.blit(self.lvl.image, ground_offset)
        crosshair.crosshair_offset = pygame.mouse.get_pos() + self.offset
        for sprite in sorted(camera_sprites.sprites(), key=lambda sprite: sprite.rect.centery and sprite not in lvl_sprites):
            offset_pos = sprite.rect.topleft - self.offset
            self.display_surface.blit(sprite.image, offset_pos)

    def get_pos(self, pos):
        self.center_target_camera(self.player)
        text_pos = pos - self.offset
        return text_pos


class Lvl(pygame.sprite.Sprite):
    def __init__(self, group, bg, name_lvl, width, hight):
        global ind
        super().__init__(camera_sprites, lvl_sprites)
        self.image = bg
        self.rect = self.image.get_rect()
        self.group = group
        self.name_lvl = name_lvl
        self.width = width
        self.hight = hight
        ind = 'lobby'
        self.cell_size = 64

        self.one_lvl = 0
        self.two_lvl = 0
        self.three_lvl = 0

        self.last_lvl = 0

        global camera
        # вызов с порталов
        camera = Camera(self.group, self)

        if self.name_lvl == 'water':
            self.water_lvl()
        elif self.name_lvl == 'land':
            self.land_lvl()

        self.sec = 0
        self.frags = 0
        self.total = 0

        self.time_up = False
        th = Thread(target=self.timer, args=())
        th.start()

    def timer(self):
        while not self.time_up:
            time.sleep(1)
            self.sec += 1

    def water_lvl(self):
        # Установка стен
        for x in range(0, self.width, self.cell_size):
            for y in range(0, self.hight + 1, self.hight):
                Wall(self.group, load_image('wall_water.png'), x, y)
        for x in range(0, self.width + 1, self.width):
            for y in range(0, self.hight, self.cell_size):
                Wall(self.group, load_image('wall_water.png'), x, y)
        Wall(self.group, load_image('wall_water.png'), self.width , self.hight)

        for x in range(0, self.width, 10 * self.cell_size):
            for y in range(self.cell_size, self.cell_size * 4, self.cell_size):
                Wall(self.group, load_image('wall_water.png'), x, y)
            for y in range(self.cell_size * 7, self.cell_size * 10, self.cell_size):
                Wall(self.group, load_image('wall_water.png'), x, y)

        # Board
        Board(self.width, self.hight, self.cell_size)
        person.rect.x, person.rect.y = 330, 320

    def land_lvl(self):
        # Установка стен
        for x in range(0, self.width, self.cell_size):
            for y in range(0, self.hight + 1, self.hight):
                Wall(self.group, load_image('wall_land.png'), x, y)
        for x in range(0, self.width + 1, self.width):
            for y in range(0, self.hight, self.cell_size):
                Wall(self.group, load_image('wall_land.png'), x, y)
        Wall(self.group, load_image('wall_land.png'), self.width, self.hight)
        # Board
        Board(self.width, self.hight, self.cell_size)
        person.rect.x, person.rect.y = 10 * self.cell_size, 8 * self.cell_size

    def open_door(self):
        for i in doors_sprites:
            i.kill()

    def close_door(self):
        for x in range(10 * self.cell_size, self.cell_size * 51, 10 * self.cell_size):
            for y in range(4, 6 + 1):
                doors_sprites.add(Wall(self.group, load_image('wall_water.png'), x, y * self.cell_size))

    def update_data_base_for_money(self, money):
        con = sqlite3.connect("database.sqlite")
        cur = con.cursor()
        cur.execute(f"UPDATE settings SET value = value + {money} WHERE title = 'money';")
        self.total += money
        con.commit()
        con.close()

    def update(self, *args):
        if self.name_lvl == 'water':
            if person.rect.x >= 11 * self.cell_size and not self.one_lvl:
                self.one_lvl = 1

                NightBorne(camera_sprites, 16 * self.cell_size, 400, 2, 10, 10)
                NightBorne(camera_sprites, 16 * self.cell_size, 320, 2, 10, 10)
                NightBorne(camera_sprites, 16 * self.cell_size, 240, 2, 10, 10)

                self.close_door()
            if self.one_lvl == 1 and not enemy_sprites:
                self.one_lvl = 2
                self.open_door()

            if person.rect.x >= 21 * self.cell_size and not self.two_lvl:
                self.two_lvl = 1

                Wizard(camera_sprites, 22 * self.cell_size, 128, 1, 5, 0)
                Wizard(camera_sprites, 28 * self.cell_size, 192, 1, 5, 0)
                Wizard(camera_sprites, 22 * self.cell_size, 512, 1, 5, 0)

                self.close_door()
            if self.two_lvl == 1 and not enemy_sprites:
                self.two_lvl = 2
                self.open_door()

            if person.rect.x >= 31 * self.cell_size and not self.three_lvl:
                self.three_lvl = 1

                NightBorne(camera_sprites, 35 * self.cell_size, 400, 2, 10, 10)
                Wizard(camera_sprites, 38 * self.cell_size, 440, 1, 5, 0)
                NightBorne(camera_sprites, 35 * self.cell_size, 320, 2, 10, 10)
                Wizard(camera_sprites, 38 * self.cell_size, 360, 1, 5, 0)
                NightBorne(camera_sprites, 35 * self.cell_size, 240, 2, 10, 10)
                Wizard(camera_sprites, 38 * self.cell_size, 280, 1, 5, 0)

                self.close_door()
            if self.three_lvl == 1 and not enemy_sprites:
                self.three_lvl = 2
                self.open_door()

            if person.rect.x >= 41 * self.cell_size and not self.last_lvl:
                self.last_lvl = 1

                NightBorne(camera_sprites, 46 * self.cell_size - 120, 5 * self.cell_size + self.cell_size / 2 - 120,
                           1.5, 100, 60)

                self.close_door()
            if self.last_lvl == 1 and not enemy_sprites:
                self.last_lvl = 2
                self.open_door()

            if self.one_lvl == 2:
                self.one_lvl = 3
                self.update_data_base_for_money(50)
            if self.two_lvl == 2:
                self.two_lvl = 3
                self.update_data_base_for_money(50)
            if self.three_lvl == 2:
                self.three_lvl = 3
                self.update_data_base_for_money(100)
            if self.last_lvl == 2:
                self.last_lvl = 3
                self.update_data_base_for_money(300)

                self.time_up = True
                print(self.sec, self.frags, self.total)
                BluePortal(camera_sprites, load_image("blue_portal.png"), 45 * self.cell_size + self.cell_size / 2,
                           y=5 * self.cell_size + self.cell_size / 2,
                           need_information=[self.sec, self.frags, self.total])
        elif self.name_lvl == 'land':
            if not self.one_lvl:
                self.one_lvl = 1
                NightBorne(camera_sprites, 1 * self.cell_size, 1 * self.cell_size, 1.6, 40, 20)
                NightBorne(camera_sprites, 2 * self.cell_size, 1 * self.cell_size, 1.6, 40, 20)
                NightBorne(camera_sprites, 1 * self.cell_size, 2 * self.cell_size, 1.6, 40, 20)
            if self.one_lvl == 1 and not enemy_sprites and not person_in_end_game:
                self.one_lvl = 2
                self.update_data_base_for_money(100)
                NightBorne(camera_sprites, 1 * self.cell_size, 1 * self.cell_size, 1.6, 40, 20)
                NightBorne(camera_sprites, 16 * self.cell_size, 0 * self.cell_size, 1.6, 40, 20)
                NightBorne(camera_sprites, 1 * self.cell_size, 10 * self.cell_size, 1.6, 40, 20)
                NightBorne(camera_sprites, 15 * self.cell_size, 10 * self.cell_size, 1.6, 40, 20)
            if self.one_lvl == 2 and not enemy_sprites and not person_in_end_game:
                self.one_lvl = 3
                self.update_data_base_for_money(150)
                NightBorne(camera_sprites, 2 * self.cell_size, 5 * self.cell_size, 1.3, 40, 20)
                NightBorne(camera_sprites, 2 * self.cell_size, 6 * self.cell_size, 1.3, 40, 20)
                NightBorne(camera_sprites, 2 * self.cell_size, 7 * self.cell_size, 1.3, 40, 20)
                Wizard(camera_sprites, 1 * self.cell_size, 8 * self.cell_size, 1, 15, 0)
            if self.one_lvl == 3 and not enemy_sprites and not person_in_end_game:
                self.one_lvl = 4
                self.update_data_base_for_money(150)
                Wizard(camera_sprites, 2 * self.cell_size, 2 * self.cell_size, 1, 15, 0)
                Wizard(camera_sprites, 17 * self.cell_size, 2 * self.cell_size, 1, 15, 0)
                Wizard(camera_sprites, 2 * self.cell_size, 13 * self.cell_size, 1, 15, 0)
                Wizard(camera_sprites, 17 * self.cell_size, 13 * self.cell_size, 1, 15, 0)
            if self.one_lvl == 4 and not enemy_sprites and not person_in_end_game:
                self.one_lvl = 5
                self.update_data_base_for_money(200)
                NightBorne(camera_sprites, 2 * self.cell_size, 2 * self.cell_size, 1.6, 200, 25)
                Wizard(camera_sprites, 2 * self.cell_size, 2 * self.cell_size, 1, 15, 0)
            if self.one_lvl == 5 and not enemy_sprites and not person_in_end_game:
                self.update_data_base_for_money(600)
                self.one_lvl = 6
                self.time_up = True
                print(self.sec, self.frags, self.total)
                GreenPortal(camera_sprites, load_image("green_portal.png"), 10 * self.cell_size,
                           y=8 * self.cell_size,
                           need_information=[self.sec, self.frags, self.total])


class Wall(pygame.sprite.Sprite):
    def __init__(self, group, image, x, y):
        super().__init__(group)
        self.add(walls_sprites)
        self.image = image
        self.rect = self.image.get_rect(topleft=(x, y))
        self.mask = pygame.mask.from_surface(self.image)


class Board:
    def __init__(self, width, height, cell_size):
        global board
        self.board = [[0] * (width // cell_size + 1) for _ in range(height // cell_size + 1)]
        for y in range(len(self.board)):
            for x in range(len(self.board[y])):
                if self.check_collision(x * cell_size, y * cell_size, walls_sprites):
                    self.board[y][x] = 1
        board = self.board
        self.print_board()

    def print_board(self):
        for i in self.board:
            print(i)

    def check_collision(self, x, y, sprite_group):
        for sprite in sprite_group:
            if sprite.rect.collidepoint(x, y):
                return True  # Наложение обнаружено
        return False  # Наложение не обнаружено


class EndGame(pygame.sprite.Sprite):
    def __init__(self, win_state, time, frags, total):
        person.rect.center = (900 / 2, 600 / 2)
        clear_other_sprites()
        global person_in_end_game
        person_in_end_game = True
        super().__init__(camera_sprites)

        self.win_state = win_state
        self.time = time
        self.frags = frags
        self.total = total

        self.image = load_image('end_game.png')
        self.rect = self.image.get_rect(topleft=(0, 0))
        for sprite in hud_sprites:
            sprite.kill()
        global ind
        ind = 'black'

    def update(self, *args):
        intro_text = ["", "",
                      f"Время: {round(self.time / 60, 2)} минут(-ы)",
                      f"Убито монстров: {self.frags}",
                      f"Заработано: {self.total}", "",
                      "Нажимите Enter, чтобы продолжить."]
        if self.win_state == 'win':
            intro_text[0] = 'Победа'
        else:
            intro_text[0] = 'Поражение'
        text_coord = (width / 2, 130)
        for line in range(len(intro_text)):
            text_coord = (text_coord[0], text_coord[1] + 40)
            if line == 0:
                font = pygame.font.Font(None, 80)
            elif line == len(intro_text) - 1:
                font = pygame.font.Font(None, 30)
            else:
                font = pygame.font.Font(None, 40)
            draw_text(screen, intro_text[line], text_coord, font, 'white', 'black')


class SetMenu(pygame.sprite.Sprite):
    def __init__(self):
        super().__init__(all_sprites)
        self.image = load_image('end_game.png')
        self.rect = self.image.get_rect()

    def update(self, *args):
        print(123)


class Maneken(pygame.sprite.Sprite):
    def __init__(self, sheet, x, y):
        super().__init__(all_sprites)
        self.frames = []
        self.cut_sheet(sheet, 7, 1)  # 7 кадров в одной строке
        self.cur_frame = 0
        self.last_update = pygame.time.get_ticks()
        self.frame_duration = 100  # Длительность кадра в миллисекундах
        self.image = pygame.transform.scale(self.frames[self.cur_frame],
                                             (int(self.frames[self.cur_frame].get_width() * 1.5),
                                              int(self.frames[self.cur_frame].get_height() * 1.5)))
        self.rect = self.image.get_rect(center=(x, y))
        self.mask = pygame.mask.from_surface(self.image)

    def cut_sheet(self, sheet, columns, rows):
        self.rect = pygame.Rect(0, 0, sheet.get_width() // columns,
                                sheet.get_height() // rows)
        for j in range(rows):
            for i in range(columns):
                frame_location = (self.rect.w * i, self.rect.h * j)
                self.frames.append(sheet.subsurface(pygame.Rect(
                    frame_location, self.rect.size)))

    def update(self, *args):
        # self.animate()
        pass

    def animate(self):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.last_update = current_time
            self.cur_frame = (self.cur_frame + 1) % len(self.frames)
            self.image = pygame.transform.scale(self.frames[self.cur_frame],
                                                (int(self.frames[self.cur_frame].get_width() * 1.5),
                                                 int(self.frames[self.cur_frame].get_height() * 1.5)))


class ShopMenu(pygame.sprite.Sprite):
    def __init__(self, group, bg):
        super().__init__(group)
        self.add(shop_menu_sprites)
        self.image = bg
        self.original_image = self.image  # Сохраняем оригинальное изображение
        self.is_open = False  # Флаг для состояния магазина
        self.flag = True

        # Увеличение изображения
        original_width, original_height = self.image.get_size()
        new_width = int(original_width * 1.5)
        new_height = int(original_height * 1.5)
        self.image = pygame.transform.scale(self.image, (new_width, new_height))
        self.rect = self.image.get_rect()
        self.rect = self.rect.move((width // 2) - (self.rect[2] // 2), -35)
        self.mask = pygame.mask.from_surface(self.image)

    def open(self):
        self.is_open = True  # Открываем магазин

    def close(self):
        self.is_open = False  # Закрываем магазин
        for sprite in item_sprites:
            sprite.kill()
        self.kill()


    def update(self, *args):
        if self.is_open:
            if self.flag:
                Items(all_sprites, load_image('Book.png'), width / 4 + 72, height / 3, book_lvl=3)
                Items(all_sprites, load_image('Book.png'), width / 2, height / 3 , book_lvl=2)
                Items(all_sprites, load_image('Book.png'), width * 3 / 4 - 72, height / 3, book_lvl=1)
                Items(all_sprites, load_image('helmet.png'), width / 4 + 72, height / 2 + 50, armor='helmet')
                Items(all_sprites, load_image('сhestplat.png'), width / 2, height / 2 + 50, armor='chestplate')
                Items(all_sprites, load_image('boots.png'), width * 3 / 4 - 72, height / 2 + 50, armor='boots')
                self.flag = False

            font = pygame.font.Font(None, 30)

            draw_text(screen, '250$', (width / 4 + 72, height / 3 + 70),
                      font, (13, 144, 104), 'white', outline_width=2)
            draw_text(screen, '1000$', (width / 2, height / 3 + 70),
                      font, (13, 144, 104), 'white', outline_width=2)
            draw_text(screen, '3000$', (width * 3 / 4 - 72, height / 3 + 70),
                      font, (13, 144, 104), 'white', outline_width=2)
            draw_text(screen, '500$', (width / 4 + 72, height / 2 + 120),
                      font, (13, 144, 104), 'white', outline_width=2)
            draw_text(screen, '1000$', (width / 2, height / 2 + 120),
                      font, (13, 144, 104), 'white', outline_width=2)
            draw_text(screen, '500$', (width * 3 / 4 - 72, height / 2 + 120,),
                      font, (13, 144, 104), 'white', outline_width=2)


            font = pygame.font.Font(None, 20)
            pos_y = height / 3 + 40

            draw_text(screen, '3 уровень', (width / 4 + 72, pos_y), font, 'black', 'white')
            draw_text(screen, '2 уровень', (width / 2, pos_y), font, 'black', 'white')
            draw_text(screen, '1 уровень', (width * 3 / 4 - 72, pos_y), font, 'black', 'white')
            pos_y = height / 2 + 90
            draw_text(screen, 'Шлем', (width / 4 + 72, pos_y), font, 'black', 'white')
            draw_text(screen, 'Кираса', (width / 2, pos_y), font, 'black', 'white')
            draw_text(screen, 'Ботинки', (width * 3 / 4 - 72, pos_y), font, 'black', 'white')

            font = pygame.font.Font(None, 20)
            draw_text(screen, 'Нажмите Z, чтобы выйти', (width / 2, height - 50),
                      font, 'black', 'white')
            font = pygame.font.Font(None, 70)
            draw_text(screen, 'Магазин', (width / 2, 100), font, (13, 144, 104), 'white', outline_width=0)
            font = pygame.font.Font(None, 50)
            draw_text(screen, f'{money}$', (width / 2, 150), font, (13, 144, 104), 'white', outline_width=0)


class Items(pygame.sprite.Sprite):
    def __init__(self, group, sheet, x, y, book_lvl=None, armor=None):
        super().__init__(group, item_sprites)
        self.image = sheet
        self.image = pygame.transform.scale(self.image, (64, 64))
        self.rect = self.image.get_rect()
        self.rect.centerx = x
        self.rect.centery = y
        self.book_lvl = book_lvl
        self.armor = armor
        self.last_click = 0

    def updata_data_base(self, item):
        global money
        if item == 'book':
            con = sqlite3.connect("database.sqlite")
            cur = con.cursor()

            res = cur.execute(f"SELECT * FROM magic WHERE get = 0 and lvl = {self.book_lvl}").fetchall()

            if len(res) != 0:
                mon = int(res[0][3])
                if money >= mon:
                    money -= mon
                    item_buy = random.choice(res)
                    cur.execute(f"UPDATE settings SET value = {money - mon} WHERE title = 'money'")
                    cur.execute(f"UPDATE magic SET get = 1 WHERE name = '{item_buy[0]}'")
            con.commit()
            con.close()
        elif item == 'armor':
            con = sqlite3.connect("database.sqlite")
            cur = con.cursor()

            res = cur.execute(f"SELECT * FROM armor WHERE get = 0 and title = '{self.armor}'").fetchall()
            print(res)
            if len(res) != 0:
                mon = int(res[0][2])
                if money >= mon:
                    money -= mon
                    item_buy = random.choice(res)
                    cur.execute(f"UPDATE settings SET value = {money - mon} WHERE title = 'money'")
                    cur.execute(f"UPDATE armor SET get = 1 WHERE title = '{item_buy[0]}'")
                    protec = cur.execute(f"SELECT protect FROM armor WHERE title = '{self.armor}'").fetchall()
                    cur.execute(f"UPDATE settings SET value = value + {protec[0][0]} WHERE title = 'protect'")
                    global protect
                    person.protect += protec[0][0]
            con.commit()
            con.close()


    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if args and args[0].type == pygame.MOUSEBUTTONDOWN:
            if args[0].button == 1:
                if self.rect.collidepoint(args[0].pos):
                    if current_time - self.last_click > 1000:
                        self.last_click = current_time
                        if self.book_lvl:
                            self.updata_data_base('book')
                        if self.armor:
                            self.updata_data_base('armor')


class Person(pygame.sprite.Sprite):
    def __init__(self, sheet_idle, sheet_walk, camera=False):
        if not camera:
            super().__init__(all_sprites)
        else:
            super().__init__(camera_sprites)
        self.add(person_sprite)
        self.can_move = True  # Флаг для контроля движения
        self.is_casting = False
        self.frames_idle = []
        self.frames_idle_left = []
        self.frames_walk = []
        self.frames_walk_left = []  # Кадры для анимации влево
        self.cut_sheet(sheet_idle, 8, 1, self.frames_idle)
        self.cut_sheet(sheet_walk, 12, 1, self.frames_walk)

        # Отразить все кадры анимации ходьбы для анимации влево
        self.frames_walk_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_walk]
        self.frames_idle_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_idle]

        self.cur_frame = 0
        self.direction = 1  # 1 - вправо, -1 - влево
        self.last_direction = 1  # Храним последнее направление

        # Проверяем, что кадры были загружены
        if not self.frames_idle or not self.frames_walk or not self.frames_walk_left:
            print("Ошибка: не удалось загрузить кадры анимации!")
            sys.exit()

        self.image = self.frames_idle[self.cur_frame]
        self.rect = self.rect.move((width // 2) - (self.rect[2] // 2), height // 3 * 2)
        self.last_update = pygame.time.get_ticks()  # Время последнего обновления
        self.frame_duration = 180  # Длительность кадра в миллисекундах
        self.speed = 2  # Скорость
        self.is_walking = False  # Флаг для проверки, идет ли персонаж
        self.mask = pygame.mask.from_surface(self.image)

        # Переменные для управления HUD
        self.hud_visible = True
        self.last_hud_toggle_time = 0
        self.hud_toggle_delay = 500  # Задержка в миллисекундах 0.5 секунду

        self.health = health
        self.protect = protect
        self.is_alive = True

    def cut_sheet(self, sheet, columns, rows, frames):
        self.rect = pygame.Rect(0, 0, sheet.get_width() // columns,
                                sheet.get_height() // rows)
        for j in range(rows):
            for i in range(columns):
                frame_location = (self.rect.w * i, self.rect.h * j)
                frames.append(sheet.subsurface(pygame.Rect(
                    frame_location, self.rect.size)))

    def open_shop(self):
        self.can_move = False
        global crosshair
        shop_menu = ShopMenu(all_sprites, load_image("shop_menu.png", pygame.Color(0, 0, 0)))
        shop_menu.open()
        crosshair.kill()
        crosshair = Crosshair(all_sprites)

    def close_shop(self):
        self.can_move = True
        if shop_menu_sprites:  # Если магазин открыт, закрываем его
            shop_menu_sprites.sprites()[0].close()

    def vanish_hud(self):
        if self.hud_visible and hud_sprites:  # Если HUD открыт, закрываем его
            hud_sprites.sprites()[0].close()
            self.hud_visible = False
        else:
            global hud
            if person_in_portal:
                hud = Hud(camera_sprites)
            else:
                hud = Hud(hud_sprites)
            self.hud_visible = True

    def update(self, *args):
        if self.is_alive:
            previous_rect = self.rect.copy()
            current_time = pygame.time.get_ticks()
            if current_time - self.last_update > self.frame_duration:
                self.last_update = current_time
                if self.is_walking and shop_menu_sprites:  # Если движется и магазин открыт
                    self.close_shop()
                keys = pygame.key.get_pressed()
                if keys[pygame.K_z] and not self.can_move:  # Если нажата Z и движение заблокировано
                    self.close_shop()
                if keys[pygame.K_v] and self.can_move:  # Если нажата V и движение разрешено
                    if current_time - self.last_hud_toggle_time > self.hud_toggle_delay:
                        self.vanish_hud()
                        self.last_hud_toggle_time = current_time  # Обновляем время последнего нажатия
                if self.health <= 0:
                    self.is_alive = False
                elif self.is_walking:
                    if self.direction == 1:
                        self.cur_frame = (self.cur_frame + 1) % len(self.frames_walk)
                        self.image = self.frames_walk[self.cur_frame]
                    else:
                        self.cur_frame = (self.cur_frame + 1) % len(self.frames_walk_left)
                        self.image = self.frames_walk_left[self.cur_frame]
                else:
                    # Обновляем изображение состояния покоя в зависимости от направления
                    if self.direction == 1:
                        self.cur_frame = (self.cur_frame + 1) % len(self.frames_idle)
                        self.image = self.frames_idle[self.cur_frame]
                    else:
                        self.cur_frame = (self.cur_frame + 1) % len(self.frames_idle)
                        self.image = self.frames_idle_left[self.cur_frame]

            # Проверка на столкновение с магазином
            if pygame.sprite.collide_mask(self, shop) and person_in_portal == False:
                self.rect.x = 521
                self.rect.y = 460
                self.open_shop()

            keys = pygame.key.get_pressed()
            dx, dy = 0, 0  # Изменение координат

            # Проверка, можно ли двигаться
            if self.can_move:
                if keys[pygame.K_a]:
                    dx = -self.speed
                    self.is_walking = True
                    self.direction = -1  # Персонаж смотрит влево
                if keys[pygame.K_d]:
                    dx = self.speed
                    self.is_walking = True
                    self.direction = 1  # Персонаж смотрит вправо
                if keys[pygame.K_w]:
                    dy = -self.speed
                    self.is_walking = True
                if keys[pygame.K_s]:
                    dy = self.speed
                    self.is_walking = True

            # Нормализация вектора движения
            if dx != 0 or dy != 0:
                norm = (dx ** 2 + dy ** 2) ** 0.5
                dx /= norm
                dy /= norm
                dx *= self.speed
                dy *= self.speed
            else:
                self.is_walking = False  # Если ничего не нажато, персонаж стоит

            # Обновляем позицию персонажа
            new_rect_x = self.rect.x + dx
            new_rect_y = self.rect.y + dy

            # Проверка на границы карты
            if person_in_portal == False:
                if new_rect_x < 0:
                    new_rect_x = 0
                if new_rect_x > width - self.rect.width:
                    new_rect_x = width - self.rect.width
                if new_rect_y < 0:
                    new_rect_y = 0
                if new_rect_y > height - self.rect.height:
                    new_rect_y = height - self.rect.height

            self.rect.x = new_rect_x
            self.rect.y = new_rect_y
            if pygame.sprite.spritecollideany(person, walls_sprites):
                self.rect.x = previous_rect.x
            if pygame.sprite.spritecollideany(person, walls_sprites):
                self.rect.x = new_rect_x
                self.rect.y = previous_rect.y
            if pygame.sprite.spritecollideany(person, walls_sprites):
                self.rect.x = previous_rect.x
                self.rect.y = previous_rect.y
        else:
            if person_in_portal:
                EndGame('lose', lvl.sec, lvl.frags, lvl.total)


class Crosshair(pygame.sprite.Sprite):
    def __init__(self, *groups):
        super().__init__(crosshair_sprites)
        if person_in_portal:
            self.add(*groups)
        self.image = load_image('Crosshair.png')
        self.speed = 2
        self.crosshair_offset = (0, 0)
        # Увеличиваем размер курсора
        self.image = pygame.transform.scale(self.image, (14, 14))
        self.rect = self.image.get_rect()
        self.rect = self.rect.move(-1000, -1000)
        pygame.mouse.set_visible(False)
        self.display_surface = pygame.display.get_surface()
        self.mask = pygame.mask.from_surface(self.image)

    def update(self, *args):
        if person_in_portal == False:
            self.rect.center = pygame.mouse.get_pos()
        else:
            x = pygame.mouse.get_pos()[0] - 7
            y = pygame.mouse.get_pos()[1] - 7
            self.display_surface.blit(crosshair.image, (x, y))


class Hud(pygame.sprite.Sprite):
    def __init__(self, groups):
        super().__init__()
        self.add(hud_sprites)
        self.speed = 2
        self.image = load_image("hud.png")
        self.original_image = self.image
        self.scaled_image = pygame.transform.scale(self.original_image,
                                                   (int(self.original_image.get_width() / 1.2),
                                                    int(self.original_image.get_height() / 1.2)))
        self.image = self.scaled_image
        self.rect = self.image.get_rect()

    def close(self):
        self.kill()

    def update(self, *args):
        screen.blit(self.image, (0, 0))
        # Отображение здоровья
        font = pygame.font.Font(None, 25)
        if person.health <= 0:
            health_surface = font.render(f"000/100", True, 'white')
        elif person.health > 99:
            health_surface = font.render(f"{person.health}/100", True, 'white')
        elif person.health < 10:
            health_surface = font.render(f"00{person.health}/100", True, 'white')
        else:
            health_surface = font.render(f"0{person.health}/100", True, 'white')
        screen.blit(health_surface, (self.rect.width / 2 - 15, 15.5))

        # Отображение защиты
        if person.protect <= 0:
            protect_surface = font.render(f"000/100", True, 'white')
        elif person.protect > 99:
            protect_surface = font.render(f"{person.protect}/100", True, 'white')
        elif person.protect < 10:
            protect_surface = font.render(f"00{person.protect}/100", True, 'white')
        else:
            protect_surface = font.render(f"{person.protect}/100", True, 'white')
        screen.blit(protect_surface, (self.rect.width / 2 - 15, 45))

        # Отображение маны
        if mana <= 0:
            mana_surface = font.render(f"000/100", True, 'white')
        elif mana > 99:
            mana_surface = font.render(f"{mana}/100", True, 'white')
        elif mana < 10:
            mana_surface = font.render(f"00{mana}/100", True, 'white')
        else:
            mana_surface = font.render(f"0{mana}/100", True, 'white')
        screen.blit(mana_surface, (self.rect.width / 2 - 15, 74.5))


class Magic(pygame.sprite.Sprite):
    def __init__(self, group, person, start_x, start_y, target_x, tarhet_y, forming, col1, row1, fly, col2, row2,
                 destroy, col3, row3, flight_duration, manaa, damage, frame_duration=90, speed=5, enemy=False):
        if person_in_portal:
            super().__init__(camera_sprites)
        else:
            super().__init__(group)
        self.frames_forming = []
        self.frames_fly = []
        self.frames_destroy = []
        self.cut_sheet(load_image(forming), col1, row1, self.frames_forming)
        self.cut_sheet(load_image(fly), col2, row2, self.frames_fly)
        self.cut_sheet(load_image(destroy), col3, row3, self.frames_destroy)
        self.cur_frame = 0
        self.state = "forming"
        self.last_update = pygame.time.get_ticks()
        self.frame_duration = frame_duration  # Длительность кадра в миллисекундах
        self.image = self.frames_forming[self.cur_frame]
        self.rect = self.image.get_rect(center=(start_x, start_y))
        self.speed = speed
        self.damage = damage
        self.start_x = start_x
        self.start_y = start_y
        self.target_x = target_x
        self.target_y = tarhet_y
        self.person = person
        self.manaa = manaa
        global mana
        if not enemy:
            if not shop_menu_sprites:
                if manaa > mana:
                    self.have_mana = False
                else:
                    mana -= manaa
                    self.person.can_move = False
                    self.have_mana = True  # Хватает ли маны?
            else:
                self.have_mana = False
        else:
            self.have_mana = True

        self.flight_duration = flight_duration  # Максимальная продолжительность полета в миллисекундах
        self.flight_start_time = pygame.time.get_ticks()
        self.damage_displayed = False
        self.vector_flag = True
        self.damage_text_position = None  # Позиция для отображения текста
        self.mask = pygame.mask.from_surface(self.image)
        self.enemy_flag = enemy

    def cut_sheet(self, sheet, columns, rows, frames):
        rect = pygame.Rect(0, 0, sheet.get_width() // columns, sheet.get_height() // rows)
        for j in range(rows):
            for i in range(columns):
                frame_location = (rect.w * i, rect.h * j)
                frame = sheet.subsurface(pygame.Rect(frame_location, rect.size))
                new_frame = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
                new_frame.blit(frame, (0, 0))
                frames.append(new_frame)

    def vector(self):
        if self.target_x == None and self.target_y == None:
            x = pygame.mouse.get_pos()[0] - self.start_x
            y = pygame.mouse.get_pos()[1] - self.start_y
        else:
            x = self.target_x - self.start_x
            y = self.target_y - self.start_y
        self.direction = pygame.math.Vector2(x, y)
        self.distance = self.direction.length()
        if self.distance > 0:
            self.direction.normalize_ip()  # Нормализуем вектор
        self.vector_flag = False

    def update(self, *args):
        if self.have_mana:
            current_time = pygame.time.get_ticks()
            if not shop_menu_sprites:
                if self.state == "forming":
                    self.rect.center = (self.person.rect.centerx, self.person.rect.centery)  # Следует за персонажем
                    if current_time - self.last_update > self.frame_duration:
                        self.last_update = current_time
                        self.cur_frame += 1
                        if self.cur_frame >= len(self.frames_forming):
                            self.cur_frame = 0
                            self.state = "fly"
                            self.person.can_move = True
                            self.person.is_casting = False

                    if self.cur_frame < len(self.frames_forming):
                        self.image = self.frames_forming[self.cur_frame]
                elif self.state == "fly":
                    if self.vector_flag:
                        self.vector()
                    self.rect.centerx += self.direction.x * self.speed
                    self.rect.centery += self.direction.y * self.speed

                    # Поворачиваем изображение в зависимости от направления движения
                    angle = math.degrees(math.atan2(self.direction.y, self.direction.x))
                    self.image = pygame.transform.rotate(self.frames_fly[0], -angle)

                    # Проверка на превышение времени полета
                    if current_time - self.flight_start_time > self.flight_duration:
                        self.state = "destroy"
                        self.cur_frame = 0

                    # Проверка на столкновение с манекеном
                    if pygame.sprite.collide_mask(self, maneken) and person_in_portal == False:
                        self.state = "destroy"
                        self.cur_frame = 0
                        self.damage_displayed = True  # Устанавливаем флаг, чтобы показать текст
                        self.damage_text_position = self.rect.center

                    if person_in_portal:
                        for spr in walls_sprites:
                            if pygame.sprite.collide_mask(self, spr):
                                self.state = "destroy"

                    # Проверка на столкновение с enemy
                    if not self.enemy_flag:
                        for enemy in enemy_sprites:
                            if pygame.sprite.collide_mask(self, enemy):
                                self.state = 'destroy'
                                self.cur_frame = 0
                                self.damage_displayed = True
                                self.damage_text_position = self.rect.center
                                enemy.health -= self.damage
                                break

                    if self.enemy_flag and pygame.sprite.collide_mask(self, person):
                        self.state = "destroy"
                        self.cur_frame = 0
                        if not person.protect:
                            person.health -= self.damage
                        elif self.damage <= person.protect:
                            person.protect -= self.damage
                        else:
                            ost_damage = self.damage - person.protect
                            person.protect = 0
                            person.health -= ost_damage

                elif self.state == "destroy":
                    if current_time - self.last_update > self.frame_duration:
                        self.last_update = current_time
                        self.cur_frame += 1
                        if self.cur_frame >= len(self.frames_destroy):
                            self.kill()

                    if self.cur_frame < len(self.frames_destroy):
                        self.image = self.frames_destroy[self.cur_frame]
            else:
                global mana
                self.kill()
                self.person.is_casting = False
                mana += self.manaa
        else:
            self.person.can_move = True
            self.person.is_casting = False
            self.kill()
        self.draw_damage_text(self.damage)

    def draw_damage_text(self, damage):
        font = pygame.font.Font(None, 30)
        if self.damage_displayed:
            if person_in_portal:
                damage_text_position = camera.get_pos(self.damage_text_position)
            else:
                damage_text_position = self.damage_text_position
            draw_text(screen, str(damage), damage_text_position, font, (255, 255, 255), (0, 0, 0))


class WaterBalloon(Magic):
    def __init__(self, group, person, start_x, start_y, target_x, target_y, en=False):
        super().__init__(group, person, start_x, start_y, target_x, target_y, "water_3_1_forming.png", 9,
                         1, "water_3_1_fly.png", 1, 1, "water_3_1_destroy.png", 6,
                         1, 2000, 5, 10, enemy=en)


class WaterArrow(Magic):
    def __init__(self, group, person, start_x, start_y, target_x, target_y, en=False):
        super().__init__(group, person, start_x, start_y, target_x, target_y, "water_2_1_forming.png", 4,
                         1, "water_2_1_fly.png", 1, 1, "water_2_1_destroy.png", 12,
                         1, 2000, 15, 35, enemy=en, speed=15, frame_duration=80)


class WaterLuch(Magic):
    def __init__(self, group, person, start_x, start_y, target_x, target_y, en=False):
        super().__init__(group, person, start_x, start_y, target_x, target_y, "water_1_1_forming.png", 23,
                         1, "water_1_1_fly.png", 4, 1, "water_1_1_destroy.png", 18,
                         1, 20000, 50, 180, enemy=en, speed=20, frame_duration=70)


class Enemy(pygame.sprite.Sprite):
    def __init__(self, group, name ,sheet_idle, row1, col1, sheet_walk, row2, col2, sheet_die, row3, col3, sheet_atack,
                 row4, col4, x, y, speed, health, damage, frame_duration, duration_magic=4000):
        super().__init__(group)
        self.add(enemy_sprites)
        self.name = name
        self.speed = speed
        self.health = health
        self.damage = damage
        self.frames_idle = []
        self.frames_idle_left = []
        self.frames_walk = []
        self.frames_walk_left = []
        self.frames_die = []
        self.frames_die_left = []
        self.frames_atack = []
        self.frames_atack_left = []
        self.cut_sheet(sheet_idle, col1, row1, self.frames_idle)
        self.cut_sheet(sheet_walk, col2, row2, self.frames_walk)
        self.cut_sheet(sheet_die, col3, row3, self.frames_die)
        self.cut_sheet(sheet_atack, col4, row4, self.frames_atack)
        # Отразить все кадры анимации ходьбы для анимации влево
        self.frames_walk_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_walk]
        self.frames_idle_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_idle]
        self.frames_die_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_die]
        self.frames_atack_left = [pygame.transform.flip(frame, True, False) for frame in self.frames_atack]

        self.cur_frame = 0
        self.direction = 1  # 1 - вправо, -1 - влево
        self.last_direction = 1  # Храним последнее направление
        self.die = True
        self.atack = False
        self.can_move = True

        # Проверяем, что кадры были загружены
        if not self.frames_idle or not self.frames_walk or not self.frames_walk_left:
            print("Ошибка: не удалось загрузить кадры анимации!")
            sys.exit()

        self.image = self.frames_idle[self.cur_frame]
        self.rect = self.image.get_rect()
        self.rect.x = x
        self.rect.y = y
        self.last_update = pygame.time.get_ticks()  # Время последнего обновления
        self.last_update_magic = pygame.time.get_ticks()  # Время последнего обновления
        self.frame_duration = frame_duration  # Длительность кадра в миллисекундах
        self.duration_magic = duration_magic
        self.is_walking = False  # Флаг для проверки, идет ли персонаж
        self.mask = pygame.mask.from_surface(self.image)

    def cut_sheet(self, sheet, columns, rows, frames):
        self.rect = pygame.Rect(0, 0, sheet.get_width() // columns,
                                sheet.get_height() // rows)
        for j in range(rows):
            for i in range(columns):
                frame_location = (self.rect.w * i, self.rect.h * j)
                frames.append(sheet.subsurface(pygame.Rect(
                    frame_location, self.rect.size)))

    def animate(self):
        if self.health <= 0:
            self.can_move = False
            if self.die:
                self.die = False
                self.cur_frame = -1
            if self.direction == 1:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_die)
                self.image = self.frames_die[self.cur_frame]
            else:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_die_left)
                self.image = self.frames_die_left[self.cur_frame]
            if self.cur_frame == len(self.frames_die) - 1:
                lvl.frags += 1
                self.kill()
        elif pygame.sprite.collide_mask(self, person) or self.atack:
            self.can_move = False
            if not self.atack:
                self.atack = True
                self.cur_frame = -1
            if self.direction == 1:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_atack)
                self.image = self.frames_atack[self.cur_frame]
            else:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_atack_left)
                self.image = self.frames_atack_left[self.cur_frame]
            if self.cur_frame == len(self.frames_atack) - 1:
                self.atack = False
                if not person.protect:
                    person.health -= self.damage
                elif self.damage <= person.protect:
                    person.protect -= self.damage
                else:
                    ost_damage = self.damage - person.protect
                    person.protect = 0
                    person.health -= ost_damage

                self.can_move = True
        elif self.is_walking:
            if self.direction == 1:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_walk)
                self.image = self.frames_walk[self.cur_frame]
            else:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_walk_left)
                self.image = self.frames_walk_left[self.cur_frame]
        else:
            # Обновляем изображение состояния покоя в зависимости от направления
            if self.direction == 1:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_idle)
                self.image = self.frames_idle[self.cur_frame]
            else:
                self.cur_frame = (self.cur_frame + 1) % len(self.frames_idle)
                self.image = self.frames_idle_left[self.cur_frame]

    def go_to_person(self):
        target_x = person.rect.centerx
        target_y = person.rect.centery
        # Вычисляем разницу между целевой точкой и текущими координатами врага
        dx = target_x - self.rect.centerx
        dy = target_y - self.rect.centery

        # Вычисляем расстояние до цели
        distance = (dx ** 2 + dy ** 2) ** 0.5

        if not pygame.sprite.collide_mask(self, person):  # Проверяем, не достиг ли враг цели
            # Нормализуем вектор направления
            dx /= distance
            dy /= distance

            # Обновляем позицию врага
            self.rect.x += dx * self.speed
            self.rect.y += dy * self.speed

            # Обновляем направление врага
            if dx > 0:
                self.direction = 1  # Вправо
            elif dx < 0:
                self.direction = -1  # Влево

            # Устанавливаем флаг ходьбы
            self.is_walking = True
        else:
            self.is_walking = False  # Если враг достиг цели, останавливаемся

    def sum_magic(self):
        target_x = person.rect.centerx
        target_y = person.rect.centery
        if target_x - self.rect.centerx < 0:
            self.direction = -1
        else:
            self.direction = 1
        WaterArrow(all_sprites, self, self.rect.centerx, self.rect.centery, target_x, target_y, en=True)

    def update(self, *args):
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update > self.frame_duration:
            self.last_update = current_time
            self.animate()
        if person_in_portal and self.can_move and self.name == 'NightBorne':
            self.go_to_person()
        if person_in_portal and self.can_move and self.name == 'wizard':
            if current_time - self.last_update_magic > self.duration_magic:
                self.last_update_magic = current_time
                self.sum_magic()


class NightBorne(Enemy):
    def __init__(self, group, x, y, speed, health, damage):
        super().__init__(group, 'NightBorne', load_image("NightBorne_idle.png"), 1, 9, load_image("NightBorne_run.png"),
                         1, 6, load_image('NightBorne_die.png'), 1, 9,
                         load_image('NightBorne_attack.png'), 1, 12, x, y, speed, health, damage, 60)

class Wizard(Enemy):
    def __init__(self, group, x, y, speed, health, damage):
        super().__init__(group, 'wizard', load_image("wizard_idle.png"), 1, 6, load_image("wizard_run.png"),
                         1, 6, load_image('Wizard_die.png'), 1, 6,
                         load_image('wizard_idle.png'), 1, 6, x, y, speed, health, damage, 100)


main_menu = MainMenu(all_sprites)
button = Button(all_sprites)
crosshair = Crosshair(all_sprites)


def start_game():
    global main_menu, button, crosshair, ground, shop, maneken, person, hud, play
    data_base()
    ground = Ground(all_sprites, load_image("grass.png"))
    shop = Shop(all_sprites)
    BluePortal(all_sprites, load_image("blue_portal.png"), width // 5 / 2)
    GreenPortal(all_sprites, load_image("green_portal.png"), width // 5 * 1.5)
    RedPortal(all_sprites, load_image("red_portal.png"), width // 5 * 2.5)
    DarkPortal(all_sprites, load_image("dark_portal.png"), width // 5 * 3.5)
    LightPortal(all_sprites, load_image("light_portal.png"), width // 5 * 4.5)
    maneken = Maneken(load_image("maneken_back.png"), 200, 400)
    person = Person(load_image('person_idle.png'), load_image('person_walk.png'))
    hud = Hud(all_sprites)
    crosshair.kill()
    crosshair = Crosshair(all_sprites)
    play = True


def summon_magic():
    # Получаем позиции игрока и курсора
    player_x, player_y = person.rect.center
    person.is_casting = True
    if person_in_portal:
        mouse_x, mouse_y = crosshair.crosshair_offset
        return player_x, player_y, mouse_x, mouse_y
    return player_x, player_y, None, None

running = True
play = False
fps = 60
pygame.display.set_caption('The Binding of Isaac: daniilok21 version')

mana_timer = 0
mana_interval = 200

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if person_in_end_game:
                    clear_other_sprites()
                    person_in_end_game = False
                    person_in_portal = False
                    start_game()
            if event.key == pygame.K_ESCAPE:
                print(123)
            if play and person.health > 0:
                if event.key == pygame.K_1:  # Если нажата клавиша "1"
                    if not person.is_casting:
                        if magic_using == 'water' and 'WaterBalloon' in can_casting:
                            use_magic = 'WaterBalloon'
                if event.key == pygame.K_4:  # Если нажата клавиша "4"
                    if not person.is_casting:
                        if magic_using == 'water' and 'WaterArrow' in can_casting:
                            use_magic = 'WaterArrow'
                if event.key == pygame.K_6:  # Если нажата клавиша "6"
                    if not person.is_casting:
                        if magic_using == 'water' and 'WaterLuch' in can_casting:
                            use_magic = 'WaterLuch'
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # 1 ЛКМ
                if play and person.health > 0:
                    if not person.is_casting:
                        if magic_using == 'water' and 'WaterBalloon' in can_casting and use_magic == 'WaterBalloon':
                            player_x, player_y, mouse_x, mouse_y = summon_magic()
                            WaterBalloon(all_sprites, person, player_x, player_y, mouse_x, mouse_y)
                        if magic_using == 'water' and 'WaterArrow' in can_casting and use_magic == 'WaterArrow':
                            player_x, player_y, mouse_x, mouse_y = summon_magic()
                            WaterArrow(all_sprites, person, player_x, player_y, mouse_x, mouse_y)
                        if magic_using == 'water' and 'WaterLuch' in can_casting and use_magic == 'WaterLuch':
                            player_x, player_y, mouse_x, mouse_y = summon_magic()
                            WaterLuch(all_sprites, person, player_x, player_y, mouse_x, mouse_y)
    # Увеличиваем мана на 1 каждые 0.2 секунды
    current_time = pygame.time.get_ticks()
    if play == True:
        if mana < mana_max:
            if current_time - mana_timer > mana_interval:
                mana += 1
                mana_timer = current_time
    screen.fill(color[ind])
    all_sprites.draw(screen)
    lvl_sprites.draw(screen)
    if person_in_portal:
        camera.custom_draw(person)
        camera_sprites.update(event)
    else:
        all_sprites.update(event)
    hud_sprites.update(event)
    crosshair_sprites.draw(screen)
    crosshair_sprites.update(event)
    pygame.display.flip()
    clock.tick(fps)