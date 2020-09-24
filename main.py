import os
import queue
from zipfile import ZipFile
import tarfile

import requests
from graphviz import Digraph

_ALLOWED_SYMBOLS = set('_-.'
                       + ''.join(chr(i) + chr(i + ord('A') - ord('a')) for i in range(ord('a'), ord('z') + 1))
                       + ''.join(chr(i) for i in range(ord('0'), ord('9') + 1)))


def download_package(name, download_all=False):
    def clean_name(dirty_name):
        for i in range(len(dirty_name)):
            if not dirty_name[i] in _ALLOWED_SYMBOLS:
                return dirty_name[:i]
        return dirty_name

    def find_link(page, file_format):
        if file_format + '</a>' in page:
            page = page[:page.rfind(file_format + '</a>')]
            return page[page.rfind('<a href="') + 9:page.rfind('">')]
        return ''

    done, tree, q = [], {}, queue.Queue()
    q.put(name)
    while not q.empty():
        try:
            name = clean_name(q.get())
            print('Getting info about ' + name)
            r = requests.get('https://pypi.org/simple/' + name)
            if r.status_code != 200:
                print('invalid package name')
                continue
            # t = r.text[r.text.find('<a href="https://files.pythonhosted.org/packages') + 9:]
            t = r.text
            # format extension, is_whell, no_deps
            for t_fmt in [('.whl', True, False), ('.tar.gz', False, False), ('.tar.bz2', False, False),
                          ('.egg', True, True), ('', True, False)]:
                r = find_link(t, t_fmt[0])
                if len(r) > 0:
                    fmt, bin_url = t_fmt, r
                    break
            else:
                print("Warning: no link found for " + name)
                continue
            if fmt[0] == '':
                print("Warning: unrecognized format for " + name)
            bin_filename = bin_url[bin_url.rfind('/') + 1:bin_url.rfind("#")]

            if os.path.isfile(bin_filename):
                print('Using cached ' + name + ': ' + bin_filename)
            else:
                print('Downloading ' + name + ' to ' + bin_filename)
                with requests.get(bin_url, stream=True) as r:
                    r.raise_for_status()
                    with open(bin_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=2 ** 18):
                            f.write(chunk)
            done.append(name)
            if fmt[2]:
                continue

            print('Extracting metadata ' + name)
            if fmt[1]:
                with ZipFile(bin_filename, 'r') as zipObj:
                    listOfFileNames = zipObj.namelist()
                    for filename in listOfFileNames:
                        if filename.endswith('.dist-info/METADATA'):
                            fn = filename
                            zipObj.extract(filename, '.')
                            break
                    else:
                        continue
            else:
                tar = tarfile.open(bin_filename, "r:gz")
                for member in tar.getmembers():
                    if member.name.endswith('.egg-info/requires.txt'):
                        fn = tar.extractfile(member).read()
                        break
                else:
                    continue
            if fn is None:
                print('No suitable metadata found for ' + name)
                continue

            print('Processing metadata ' + name)
            deps = []
            if fmt[1]:
                with open(fn, 'r') as metadata:
                    text = metadata.read()
                while 'Requires-Dist: ' in text:
                    text = text[text.find('Requires-Dist: ') + len('Requires-Dist: '):]
                    d = text[:text.find('\n')]
                    if not download_all and ' ; extra == ' in d:
                        continue
                    d = clean_name(d)
                    if len(d) > 0:
                        deps.append(d)
            else:
                text = fn.decode()
                for line in text.splitlines():
                    nn = clean_name(line)
                    if len(nn) > 0:
                        deps.append(nn)

            print('Cleaning up after ' + name)
            if fmt[1]:
                try:
                    os.remove(filename)
                    os.rmdir(filename[:filename.find('/')])
                except OSError as e:
                    print('Can\'t clean up: ' + str(e))
            if len(deps) > 0:
                tree[name] = []
                for dep in deps:
                    if not download_all and ' ; extra == ' in dep:
                        continue
                    dep = clean_name(dep)
                    if len(dep) > 0:
                        tree[name].append(dep)

                print(name + ' Depencies: ' + str(tree[name]) + '; binary file: ' + bin_filename)

                for n in tree[name]:
                    if n not in done:
                        q.put(n)

        except Exception as e:
            print("Error:", e)
            continue
    return tree


def draw_tree(name, tree):
    g = Digraph(name, filename=name + '.gv')
    g.attr('node', shape='doublecircle')
    g.node(name)
    g.attr('node', shape='circle')
    if tree is not None:
        for name in tree:
            for dep in tree[name]:
                g.edge(name, dep)
    g.view()


def main(name=None, download_all=False):
    if name is None:
        name = input('Enter package to download: ')
    deps = download_package(name, download_all)
    print("Building dependency graph")
    draw_tree(name, deps)
    print("Downloaded " + str(len(deps) + 1) + " packages succesfully")


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        main(sys.argv[1], len(sys.argv) > 2)
    else:
        main()
