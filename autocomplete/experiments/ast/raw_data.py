import json
from tqdm import tqdm

from autocomplete.lib.log import tqdm_lim

ENCODING = 'ISO-8859-1'
EMPTY_TOKEN = '<emp>'  
UNKNOWN_TOKEN = '<unk>'  
EOF_TOKEN = 'EOF' 


class OneHotConverter:
    def __init__(self, file_terminals, file_non_terminals):
        self.terminals, self.terminal_idx = DataUtils.read_terminals_json(file_terminals)
        self.non_terminals, self.non_terminal_idx = DataUtils.read_non_terminals_json(file_non_terminals)

    def convert_file(self, src_file, dst_file, lim=None):
        f_read = open(src_file, mode='r', encoding=ENCODING)
        f_write = open(dst_file, mode='w', encoding=ENCODING)

        c = 0
        for l in tqdm(f_read, total=100000):
            c += 1
            raw_json = json.loads(l)

            converted_json = []
            for node in raw_json:
                if node == 0:
                    break

                N = node['N']
                T = node['T']

                if T not in self.terminal_idx.keys():
                    raise Exception('Unknown terminal: {}'.format(T))

                n_id = len(self.non_terminal_idx.keys())
                if N in self.non_terminal_idx.keys():
                    n_id = self.non_terminal_idx[N]

                converted_json.append({
                    'N': n_id,
                    'T': self.terminal_idx[T],
                    'd': node['d']
                })

            f_write.write(json.dumps(converted_json))
            f_write.write('\n')

            if (lim is not None) and (c == lim):
                break


class JsonConverter:
    @staticmethod
    def convert_file(raw_file, dest_file, terminals_file,
                     encoding=ENCODING, append_eof=True, lim=None, last_is_zero=False):
        f_read = open(raw_file, mode='r', encoding=encoding)
        f_write = open(dest_file, mode='w', encoding=encoding)
        terminals = set(DataUtils.read_json(file=terminals_file))

        c = 0
        for l in tqdm(f_read, total=min(lim, 100000)):
            c += 1
            raw_json = json.loads(l)
            converted_json = JsonConverter._convert_json_(raw_json, terminals, append_eof, last_is_zero=last_is_zero)

            converted_json_string = json.dumps(converted_json)
            f_write.write(converted_json_string)
            f_write.write('\n')

            if (lim is not None) and (c == lim):
                break

    @staticmethod
    def _convert_json_(raw_json, terminals_set, append_eof, last_is_zero=False):
        left_child, right_sibling = DataUtils.get_left_child_right_sibling(
            raw_json=raw_json,
            append_eof=append_eof
        )

        if last_is_zero:
            output_json = [{} for i in range(len(raw_json) - 1)]
        else:
            output_json = [{} for i in range(len(raw_json))]

        output_json[0]['d'] = 0
        cur_id = 0
        for (node_id, node) in enumerate(raw_json):
            if node == 0:
                continue

            N = DataUtils.encode_non_terminal(node_id, node, left_child, right_sibling)

            if 'value' not in node:
                T = EMPTY_TOKEN
            elif node['value'] not in terminals_set:
                T = UNKNOWN_TOKEN
            else:
                T = node['value']

            if 'children' in node:
                c_d = output_json[cur_id]['d']
                for c in node['children']:
                    output_json[c]['d'] = c_d + 1

            output_json[cur_id]['N'] = N
            output_json[cur_id]['T'] = T

            cur_id += 1

        if append_eof:
            output_json.append({
                'N': EOF_TOKEN,
                'T': EMPTY_TOKEN,
                'd': 1
            })

        return output_json


class TokensRetriever:
    def __init__(self):
        self.non_terminals = {}
        self.terminals = {}

    def get_and_write_tokens(
            self,
            dataset,
            non_terminal_dest,
            terminal_dest,
            encoding=ENCODING,
            append_eof=True,
            lim=None
    ):
        c = 0
        with open(dataset, mode='r', encoding=ENCODING) as f:
            for l in tqdm_lim(f, total=lim, lim=100000):
                c += 1
                self._process_single_json_(json.loads(l), append_eof=append_eof)

                if (lim is not None) and (c == lim):
                    break

        with open(non_terminal_dest, mode='w', encoding=encoding) as f:
            f.write(json.dumps(list(self.non_terminals.keys())))

        with open(terminal_dest, mode='w', encoding=encoding) as f:
            sorted_terminals = sorted(self.terminals.keys(), key=lambda key: self.terminals[key], reverse=True)
            f.write(json.dumps(([EMPTY_TOKEN] + sorted_terminals)[:50000]))

    def _process_single_json_(self, raw_json, append_eof):
        left_child, right_sibling = DataUtils.get_left_child_right_sibling(
            raw_json=raw_json,
            append_eof=append_eof
        )

        for (node_id, node) in enumerate(raw_json):
            if node == 0:
                break

            node_type = DataUtils.encode_non_terminal(node_id, node, left_child, right_sibling)
            if node_type not in self.non_terminals.keys():
                self.non_terminals[node_type] = 0
            self.non_terminals[node_type] += 1

            if 'value' in node:
                node_value = node['value']
                if node_value not in self.terminals.keys():
                    self.terminals[node_value] = 0
                self.terminals[node_value] += 1


class DataUtils:
    @staticmethod
    def read_terminals_json(file):
        terminals = DataUtils.read_json(file)
        terminals.append(UNKNOWN_TOKEN)

        terminal_idx = {}
        for i in range(len(terminals)):
            terminal_idx[terminals[i]] = i

        return terminals, terminal_idx

    @staticmethod
    def read_non_terminals_json(file):
        non_terminals = DataUtils.read_json(file)
        non_terminals.append(EOF_TOKEN)

        non_terminal_idx = {}
        for i in range(len(non_terminals)):
            non_terminal_idx[non_terminals[i]] = i

        return non_terminals, non_terminal_idx

    @staticmethod
    def read_json(file):
        return json.loads(open(file, mode='r', encoding=ENCODING).read())

    @staticmethod
    def get_left_child_right_sibling(raw_json, append_eof=True):
        left_child = set()
        right_sibling = set()

        for (node_id, node) in enumerate(raw_json):
            if node == 0:
                break

            if 'children' in node:  
                has_right_sibling_count = len(node['children']) - 1  
                if append_eof and node['type'] == 'Program': 
                    has_right_sibling_count = len(node['children'])

                if 'id' in node:
                    left_child.add(node['id'])  
                else:
                    left_child.add(node_id)

                for i in range(has_right_sibling_count):
                    right_sibling.add(node['children'][i])

        return left_child, right_sibling

    @staticmethod
    def encode_non_terminal(node_id, node, left_child, right_sibling):
        node_type = node['type']
        if 'id' in node:
            node_id = node['id']

        if node_id in left_child:
            node_type += '1'
        else:
            node_type += '0'

        if node_id in right_sibling:
            node_type += '1'
        else:
            node_type += '0'

        return node_type
