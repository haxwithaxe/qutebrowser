# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:

# Copyright 2014-2015 Florian Bruhin (The Compiler) <mail@qutebrowser.org>
#
# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Saving things to disk periodically."""

from PyQt5.QtCore import pyqtSlot, QObject

from qutebrowser.config import config
from qutebrowser.commands import cmdutils
from qutebrowser.utils import utils, log, message


class Saveable:

    """A single thing which can be saved.

    Attributes:
        _name: The naem of the thing to be saved.
        _dirty: Whether the saveable was changed since the last save.
        _save_handler: The function to call to save this Saveable.
        _save_on_exit: Whether to always save this saveable on exit.
        _config_opt: A (section, option) tuple of a config option which decides
                     whether to autosave or not. None if no such option exists.
    """

    def __init__(self, name, save_handler, changed=None, config_opt=None):
        self._name = name
        self._dirty = False
        self._save_handler = save_handler
        self._config_opt = config_opt
        if changed is not None:
            changed.connect(self.mark_dirty)
            self._save_on_exit = False
        else:
            self._save_on_exit = True

    def __repr__(self):
        return utils.get_repr(self, name=self._name, dirty=self._dirty,
                              save_handler=self._save_handler,
                              config_opt=self._config_opt,
                              save_on_exit=self._save_on_exit)

    @pyqtSlot()
    def mark_dirty(self):
        """Mark this saveable as dirty (having changes)."""
        log.save.debug("Marking {} as dirty.".format(self._name))
        self._dirty = True

    def save(self, is_exit=False, explicit=False):
        """Save this saveable.

        Args:
            is_exit: Whether we're currently exiting qutebrowser.
            explicit: Whether the user explicitely requested this save.
        """
        if (self._config_opt is not None and
                (not config.get(*self._config_opt)) and
                (not explicit)):
            log.save.debug("Not saving {} because autosaving has been "
                           "disabled by {cfg[0]} -> {cfg[1]}.".format(
                               self._name, cfg=self._config_opt))
            return
        do_save = self._dirty or (self._save_on_exit and is_exit)
        log.save.debug("Save of {} requested - dirty {}, save_on_exit {}, "
                       "is_exit {} -> {}".format(
                           self._name, self._dirty, self._save_on_exit,
                           is_exit, do_save))
        if do_save:
            self._save_handler()
            self._dirty = False


class SaveManager(QObject):

    """Responsible to save 'saveables' periodically and on exit.

    Attributes:
        saveables: A dict mapping names to Saveable instances.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.saveables = {}

    def __repr__(self):
        return utils.get_repr(self, saveables=self.saveables)

    def add_saveable(self, name, save, changed=None, config_opt=None):
        """Add a new saveable.

        Args:
            name: The name to use.
            save: The function to call to save this saveable.
            changed: The signal emitted when this saveable changed.
            config_opt: A (section, option) tuple deciding whether to autosave
                       or not.
        """
        if name in self.saveables:
            raise ValueError("Saveable {} already registered!".format(name))
        self.saveables[name] = Saveable(name, save, changed, config_opt)

    def save(self, name, is_exit=False, explicit=False):
        """Save a saveable by name.

        Args:
            is_exit: Whether we're currently exiting qutebrowser.
            explicit: Whether this save operation was triggered explicitely.
        """
        self.saveables[name].save(is_exit=is_exit, explicit=explicit)

    @cmdutils.register(instance='save-manager', name='save')
    def save_command(self, win_id: {'special': 'win_id'},
                     *what: {'nargs': '*'}):
        """Save configs and state.

        Args:
            win_id: The window this command is executed in.
            *what: What to save (`config`/`key-config`/`cookies`/...).
                   If not given, everything is saved.
        """
        if what:
            explicit = True
        else:
            what = self.saveables
            explicit = False
        for key in what:
            if key not in self.saveables:
                message.error(win_id, "{} is nothing which can be "
                              "saved".format(key))
            else:
                try:
                    self.save(key, explicit=explicit)
                except OSError as e:
                    message.error(win_id, "Could not save {}: "
                                  "{}".format(key, e))