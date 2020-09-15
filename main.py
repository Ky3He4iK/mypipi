from zipfile import ZipFile
import os
import tarfile

import requests


def download_package(name, done=None, tree=None):
    def clean_name(n):
        ALLOWED = '_-.'
        i = 0
        while i < len(n):
            if not (n[i].isalnum() or n[i] in ALLOWED):
                return n[:i]
            i += 1
        return n

    try:
        name = clean_name(name)
        print('Getting info about ' + name)
        r = requests.get('https://pypi.org/project/' + name)
        if r.status_code != 200:
            print('invalid package name')
            return None, None
        t = r.text[r.text.find('<a href="https://files.pythonhosted.org/packages') + 9:]
        no_deps = False
        if '.whl">' in t:
            bin_url = t[:t.find('.whl">') + 4]
            is_wheel = True
        elif '.tar.gz">' in t:
            bin_url = t[:t.find('.tar.gz">') + 7]
            is_wheel = False
        elif '.tar.bz2">' in t:
            bin_url = t[:t.find('.tar.bz2">') + 8]
            is_wheel = False
        elif '.egg">' in t:
            bin_url = t[:t.find('.egg">') + 4]
            is_wheel = True
            no_deps = True
        else:
            bin_url = t[:t.find('">')]
            is_wheel = True
            print("Warning: unrecognized format")
        if '<a href' in bin_url:
            bin_url = bin_url[bin_url.rfind('<a href="') + 9:]
        if '">' in bin_url:
            bin_url = bin_url[:bin_url.find('\">')]
        bin_filename = bin_url[bin_url.rfind('/') + 1:]

        if os.path.isfile(bin_filename):
            print('Using cached ' + name + ': ' + bin_filename)
        else:
            print('Downloading ' + name + ' to ' + bin_filename, end='', flush=True)
            with requests.get(bin_url, stream=True) as r:
                r.raise_for_status()
                with open(bin_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=2 ** 18):
                        f.write(chunk)
                        print('.', end='', flush=True)
            print()
        if done is None:
            done = []
        done.append(name)

        if no_deps:
            return bin_filename, tree

        print('Extracting metadata ' + name)

        fn = None
        if is_wheel:
            with ZipFile(bin_filename, 'r') as zipObj:
                listOfFileNames = zipObj.namelist()
                for filename in listOfFileNames:
                    if filename.endswith('.dist-info/METADATA'):
                        fn = filename
                        zipObj.extract(filename, '.')
                        break
        else:
            tar = tarfile.open(bin_filename, "r:gz")
            for member in tar.getmembers():
                if member.name.endswith('.egg-info/requires.txt'):
                    fn = tar.extractfile(member).read()
        if fn is None:
            print('No suitable metadata found for ' + name)
            return bin_filename, tree

        print('Processing metadata ' + name)
        dep = []
        if is_wheel:
            with open(fn, 'r') as metadata:
                text = metadata.read()
            while 'Requires-Dist: ' in text:
                text = text[text.find('Requires-Dist: ') + len('Requires-Dist: '):]
                d = text[:min(text.find(' '), text.find('\n'))]
                if '[' in d:
                    d = d[:d.find('[')]
                if '\n' in d:
                    d = d[:d.find('\n')]
                d = clean_name(d)
                if len(d) > 0:
                    dep.append(d)
        else:
            text = fn.decode()
            for line in text.splitlines():
                nn = clean_name(line)
                if len(nn) > 0:
                    dep.append(nn)

        print('Cleaning up after ' + name)
        if is_wheel:
            try:
                os.remove(filename)
                os.rmdir(filename[:filename.find('/')])
            except OSError as e:
                print('Can\'t clean up: ' + str(e))

        print(name + ' Depencies: ' + str(dep) + '; binary file: ' + bin_filename)
        if tree is None:
            tree = {}
        tree[name] = dep

        for n in dep:
            if n not in done:
                download_package(n, done, tree)

        return bin_filename, tree
    except Exception as e:
        print("Error:", e)
        return None, None


def print_tree(name, tree, margin='', history=[]):
    if len(name) == 0:
        return
    print(margin + name)
    margin = margin.replace('└', ' ').replace('├', '│') + '├'
    if name in history:
        print(margin[:-1] + '└....')
        return
    history.append(name)
    if tree is None or name not in tree:
        return
    l, i = len(tree[name]), 1
    for dep in tree[name]:
        if i == l:
            margin = margin[:-1] + '└'
        print_tree(dep, tree, margin, history)
        i += 1


if __name__ == '__main__':
    name = input('Enter package to download: ')
    bin_filename, tree = download_package(name)
    print("Saved main file as " + str(bin_filename))
    print("Dependency tree:")
    print_tree(name, tree)
