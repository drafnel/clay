#!/usr/bin/env python

from __future__ import with_statement
from string import Template
import re, fnmatch, os

VERSION = "0.8.0"

TEST_FUNC_REGEX = r"^(void\s+(test_%s__(\w+))\(\s*(void)?\s*\))\s*\{"

CLAY_HEADER = """
/*
 * Clay v0.7.0
 *
 * This is an autogenerated file. Do not modify.
 * To add new unit tests or suites, regenerate the whole
 * file with `./clay`
 */
"""

TEMPLATE_SUITE = Template(
r"""
    {
        "${clean_name}",
        ${initialize},
        ${cleanup},
        ${cb_ptr}, ${cb_count}
    }
""")

def main():
    from optparse import OptionParser

    parser = OptionParser()

    parser.add_option('-c', '--clay-path', dest='clay_path')
    parser.add_option('-v', '--report-to', dest='print_mode', default='stdout')

    options, args = parser.parse_args()

    for folder in args:
        builder = ClayTestBuilder(folder,
            clay_path = options.clay_path,
            print_mode = options.print_mode)

        builder.render()


class ClayTestBuilder:
    def __init__(self, path, clay_path = None, print_mode = 'stdout'):
        self.declarations = []
        self.callbacks = []
        self.suites = []
        self.suite_list = []

        self.clay_path = os.path.abspath(clay_path) if clay_path else None
        self.print_mode = print_mode

        self.path = os.path.abspath(path)
        self.modules = ["clay_sandbox.c", "clay_fixtures.c", "clay_fs.c"]

        print("Loading test suites...")

        for root, dirs, files in os.walk(self.path):
            module_root = root[len(self.path):]
            module_root = [c for c in module_root.split(os.sep) if c]
            dirs.sort()

            tests_in_module = fnmatch.filter(files, "*.c")
            tests_in_module.sort()

            for test_file in tests_in_module:
                full_path = os.path.join(root, test_file)
                test_name = "_".join(module_root + [test_file[:-2]])

                with open(full_path) as f:
                    self._process_test_file(test_name, f.read())

        if not self.suites:
            raise RuntimeError(
                'No tests found under "%s"' % folder_name)

    def render(self):
        main_file = os.path.join(self.path, 'clay_main.c')
        with open(main_file, "w") as out:
            template = Template(self._load_file('clay.c'))

            output = template.substitute(
                clay_print = self._get_print_method(),
                clay_modules = self._get_modules(),

                suites_str = ", ".join(self.suite_list),

                test_callbacks = ",\n\t".join(self.callbacks),
                cb_count = len(self.callbacks),

                test_suites = ",\n\t".join(self.suites),
                suite_count = len(self.suites),
            )

            out.write(output)

        header_file = os.path.join(self.path, 'clay.h')
        with open(header_file, "w") as out:
            template = Template(self._load_file('clay.h'))

            output = template.substitute(
                extern_declarations = "\n".join(self.declarations),
            )

            out.write(output)

        print ('Written Clay suite to "%s"' % self.path)

    #####################################################
    # Internal methods
    #####################################################
    def _get_print_method(self):
        return {
                'stdout' : 'printf(__VA_ARGS__)',
                'stderr' : 'fprintf(stderr, __VA_ARGS__)',
                'silent' : ''
        }[self.print_mode]

    def _load_file(self, filename):
        if self.clay_path:
            filename = os.path.join(self.clay_path, filename)
            with open(filename) as cfile:
                return cfile.read()

        else:
            import zlib, base64, sys
            content = CLAY_FILES[filename]

            if sys.version_info >= (3, 0):
                content = bytearray(content, 'utf_8')
                content = base64.b64decode(content)
                content = zlib.decompress(content)
                return str(content)
            else:
                content = base64.b64decode(content)
                return zlib.decompress(content)

    def _get_modules(self):
        return "\n".join(self._load_file(f) for f in self.modules)

    def _parse_comment(self, comment):
        comment = comment[2:-2]
        comment = comment.splitlines()
        comment = [line.strip() for line in comment]
        comment = "\n".join(comment)

        return comment

    def _process_test_file(self, test_name, contents):
        regex_string = TEST_FUNC_REGEX % test_name
        regex = re.compile(regex_string, re.MULTILINE)

        callbacks = []
        initialize = cleanup = "{NULL, NULL, 0}"

        for (declaration, symbol, short_name, _) in regex.findall(contents):
            self.declarations.append("extern %s;" % declaration)
            func_ptr = '{"%s", &%s, %d}' % (
                short_name, symbol, len(self.suites)
            )

            if short_name == 'initialize':
                initialize = func_ptr
            elif short_name == 'cleanup':
                cleanup = func_ptr
            else:
                callbacks.append(func_ptr)

        if not callbacks:
            return

        clean_name = test_name.replace("_", "::")

        suite = TEMPLATE_SUITE.substitute(
            clean_name = clean_name,
            initialize = initialize,
            cleanup = cleanup,
            cb_ptr = "&_all_callbacks[%d]" % len(self.callbacks),
            cb_count = len(callbacks)
        ).strip()

        self.callbacks += callbacks
        self.suites.append(suite)
        self.suite_list.append(clean_name)

        print("  %s (%d tests)" % (clean_name, len(callbacks)))
