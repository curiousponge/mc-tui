import curses
from curses import wrapper
import subprocess
from time import sleep
from threading import Thread
import os
import json
import tempfile

s3_base = ""
mc_config_path = os.path.expanduser("~/.mc/config.json")

class Label():
    def __init__(self, id, key, size, last_modified, style=curses.A_NORMAL):
        self.id = id
        self.key = key
        self.size = size
        self.last_modified = last_modified
        self.style = style

        if len(self.last_modified) > 0:
            self.day_modified = self.last_modified.split("T")[0]
            self.time_modified_detailed = self.last_modified.split("T")[1][:-1] # To exclude the 'Z' at the end
            self.time_modified_zoneless = self.time_modified_detailed.split("+")[0]
            self.time_modified_rough = self.time_modified_zoneless.split("+")[0]
        else:
            self.day_modified = ""
            self.time_modified_detailed = ""
            self.time_modified_rough = ""


def size_compactor(size):
    GB = 10**9
    MB = 10**6
    KB = 10**3
    if size < KB:
        unit = "B"
        amount = size

        return f"{amount} {unit}"

    elif size > GB:
        unit = "GB"
        amount = size / GB
    elif size > MB:
        unit = "MB"
        amount = size / MB
    # elif size > KB:
    #     unit = "KB"
    #     amount = size / KB
    else:
        unit = "KB"
        amount = size / KB

    # return f"{amount:06.2f}{unit}"
    return f"{amount:.2f} {unit}"


def generate_content(cursor, path, lines, dot_ok=False):
    s3_content_bytes = subprocess.check_output(f'mc ls --json {path}', shell=True)
    s3_content_str = s3_content_bytes.decode()
    content_string_list = s3_content_str.split("\n")[:-1]
    content_json_list = [json.loads(content_string) for content_string in content_string_list]
    labels = []
    for content_json in content_json_list:
        if content_json["type"] == "file":
            size = content_json["size"]
            size = size_compactor(int(size))
            last_modified = content_json["lastModified"]
        else:
            size = ""
            last_modified = ""

        object_name = content_json["key"]
        if dot_ok:
            # label = Label(len(labels), f'{day_modified} {object_name}')
            label = Label(len(labels), object_name, size, last_modified)
            labels.append(label)
        elif not content_json["key"].startswith("."):
            label = Label(len(labels), object_name, size, last_modified)
            labels.append(label)
        else:
            continue
    if labels:
        labels[0].style = curses.A_REVERSE
    else:
        labels = [Label(0, "EMPTY DIRECTORY, GO BACK", "", "")]


    return labels

def show_labels(labels, win, cursor, cursor_top, cursor_bot, lines, columns, colors):
    if cursor > cursor_bot:
        cursor_top += 1
        cursor_bot += 1
    elif cursor < cursor_top:
        cursor_top -= 1
        cursor_bot -= 1
    for idx, label in enumerate(labels[cursor_top:cursor_bot+1]):
        if len(label.last_modified) > 0:
            win.addstr(f"{label.day_modified} {label.time_modified_rough}" , label.style | colors["BLACK_N_SEA"])
            # TODO: Fix this hardcoded number below into something dynamic
            size_str_gap = 9 - len(label.size)
            win.addstr(f"  {' '*size_str_gap}")
            # TODO: Fix sometimes time has extra +03:blabla
            win.addstr(f"{label.size}", label.style | colors["BLACK_N_SEA"])
            win.addstr(f"  ")
            win.addstr(f"{label.key}\n", label.style | colors["BLACK_N_SEA"])
        else:
            win.addstr(f"                                ")
            win.addstr(f"{label.key}\n", label.style | colors["BLACK_N_SEA"])


    win.refresh()

    return cursor_top, cursor_bot


# def show_preview(labels, pad, cursor, cursor_top, cursor_bot, lines, columns):
def show_preview(preview_content, win, columns, lines):
    win.addstr(preview_content)

    win.refresh()

# Utility function to view all colors possible
def show_all_colors(stdscr):
    stdscr.clear()
    for i in range(curses.COLORS):
        curses.init_pair(i + 1, i, -1)
        try:
            for i in range(255):
                stdscr.addstr(f"{i-1} ", curses.color_pair(i))
        except:
            pass
    stdscr.refresh()
    stdscr.getch()

def main(stdscr):
    curses.start_color()
    # curses.use_default_colors()
    # show_all_colors(stdscr)
    curses.init_pair(1, 50, 16)
    curses.init_pair(2, 14, 14)
    colors = {
              "BLACK_N_SEA" : curses.color_pair(1),
              "BLACK_N_WEIRD" : curses.color_pair(2)
             }
    stdscr.clear()
    stdscr.bkgd(" ", colors["BLACK_N_SEA"])
    stdscr.refresh()
    curses.curs_set(0)
    lines = curses.LINES
    columns = curses.COLS
    cursor = 0 # which position is cursor at
    cursor_top = 0
    cursor_bot = lines-3
    dot_ok = False
    preview_mode = False
    path = s3_base
    win = curses.newwin(lines+1, columns+1, 2, 0)
    win_cwd = curses.newwin(1, columns+1, 0, 0)
    win_cwd.clear()
    win_cwd.bkgd(" ", colors["BLACK_N_SEA"])
    win_cwd.refresh()
    win.keypad(True)
    win.clear()
    win.bkgd(" ", colors["BLACK_N_SEA"])
    win.refresh()
    labels = generate_content(cursor, path, lines)
    cursor_top, cursor_bot = show_labels(labels, win, cursor, cursor_top, cursor_bot, lines, columns, colors)
    with open(mc_config_path, "r") as f:
        file = json.load(f)
    if "aliases" in file.keys():
        items = list(file["aliases"].keys())
    elif "hosts" in file.keys():
        items = list(file["hosts"].keys())
    labels = [Label(idx, item, "", "") for idx, item in enumerate(items)]
    labels[0].style = curses.A_REVERSE
    remove_flag = False

    key = None

    while True:
        preview_mode = False
        win.clear()
        if key in ["j", "KEY_DOWN"] and cursor < len(labels)-1:
            cursor += 1
            labels[cursor-1].style = curses.A_NORMAL
            labels[cursor].style = curses.A_REVERSE
        if key in ["k", "KEY_UP"] and cursor > 0:
            cursor -= 1
            labels[cursor+1].style = curses.A_NORMAL
            labels[cursor].style = curses.A_REVERSE
        if key in ["h", "KEY_LEFT"]:
            if path[-1] == "/":
                path = path[:-1]
            path_items = path.split("/")
            path_items.pop(-1)
            path = "/".join(path_items)
            if path:
                labels = generate_content(cursor=cursor, path=path, lines=lines)
            else:
                with open(mc_config_path, "r") as f:
                    file = json.load(f)
                if "aliases" in file.keys():
                    items = list(file["aliases"].keys())
                elif "hosts" in file.keys():
                    items = list(file["hosts"].keys())
                labels = [Label(idx, item, "", "") for idx, item in enumerate(items)]
                labels[0].style = curses.A_REVERSE
            cursor = 0
            cursor_top = 0
            cursor_bot = lines-3
        if key in ["l", "KEY_RIGHT"]:
            tail = labels[cursor].key.split()[-1]
            path = os.path.join(path, tail)
            labels = generate_content(cursor=cursor, path=path, lines=lines)
            cursor = 0
            cursor_top = 0
            cursor_bot = lines-3
        if key == "y":
            tail = labels[cursor].key.split()[-1]
            yank_path = os.path.join(path, tail)
            if yank_path[-1] == "/":
                yank_path = yank_path[:-1]
        if key == "q":
            curses.curs_set(1)
            return
        if key == "p":
            win.clear()
            win.addstr("Copying...\n")
            win.refresh()
            subprocess.call(["mc", "cp", "--recursive", f"{yank_path}", f"{path}"])
            win.clear()
            labels = generate_content(cursor=cursor, path=path, lines=lines)
            cursor = 0
            cursor_top = 0
            cursor_bot = lines-3
        if key == "D":
            if remove_flag:
                remove_flag = False
                tail = labels[cursor].key.split()[-1]
                remove_path = os.path.join(path, tail)
                win.clear()
                win.addstr("Removing...\n")
                win.refresh()
                subprocess.call(["mc", "rm", "--recursive", "--dangerous", "--force", f"{remove_path}"])
                win.clear()
                labels = generate_content(cursor=cursor, path=path, lines=lines)
                cursor = 0
                cursor_top = 0
                cursor_bot = lines-3
        if key == "d":
            remove_flag = True
        else:
            remove_flag = False
        if key == " ":
            if path.startswith("/home"):
                path = s3_base
            else:
                path = os.path.expanduser("~")
            labels = generate_content(cursor=cursor, path=path, lines=lines)
            cursor = 0
            cursor_top = 0
            cursor_bot = lines-3
        if key == chr(127): # for backspace
            if dot_ok:
                labels = generate_content(cursor=cursor, path=path, lines=lines, dot_ok=False)
                dot_ok = False
                cursor = 0
                cursor_top = 0
                cursor_bot = lines-3
            else:
                labels = generate_content(cursor=cursor, path=path, lines=lines, dot_ok=True)
                dot_ok = True
                cursor = 0
                cursor_top = 0
                cursor_bot = lines-3
        if key == "\t":
            preview_mode = True
            tail = labels[cursor].key.split()[-1]
            preview_path = os.path.join(path, tail)
            preview_content = subprocess.check_output(f'mc head {preview_path}', shell=True)
            # file_content_bytes = subprocess.check_output(f'head /tmp/dumm.temp', shell=True)


        if key == "\n":
            # preview_mode = True
            tail = labels[cursor].key.split()[-1]
            preview_path = os.path.join(path, tail)
            with tempfile.NamedTemporaryFile(suffix=".tmp") as tf: # to be changed to the extension of the file, maybe
                temp_content = subprocess.check_output(f'mc cat {preview_path}', shell=True)
                # tf.flush()
                # tf.seek(0)
                # temp_content = tf.read().decode()
            # with open("/tmp/dumm.temp", "r") as f:
                # temp_content = f.read()
                # preview_content = "\n".join(temp_content.split("\n")[:6]) # get the first five lines

            EDITOR = os.environ.get('EDITOR', 'nvim') # that easy!
            # initial_message = temp_content.encode()
            initial_message = temp_content

            with tempfile.NamedTemporaryFile(suffix=".tmp") as tf:
                tf.write(initial_message)
                tf.flush()
                subprocess.call([EDITOR, tf.name])

                tf.seek(0)
                subprocess.check_output(f'mc cp {tf.name} {preview_path}', shell=True)
            # TODO: get arrow keys back after editing

            # Fixes the cursor appearing after editing
            curses.curs_set(1)
            curses.curs_set(0)
            win.keypad(True)

        if preview_mode:
            show_preview(preview_content, win, columns, lines)
        else:
            cursor_top, cursor_bot = show_labels(labels, win, cursor, cursor_top, cursor_bot, lines, columns, colors)

        win_cwd.clear()
        if path:
            slashless_path = path[:-1] if path[-1] == "/" else path
        else:
            slashless_path = "PICK A HOST"
        win_cwd.addstr(f"                             @) {slashless_path}")
        win_cwd.refresh()
        key = win.getkey()


    stdscr.getch()


wrapper(main)
