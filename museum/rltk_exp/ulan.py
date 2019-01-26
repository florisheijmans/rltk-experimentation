import re
import time
import rltk


name_filter = re.compile('[^A-Za-z0-9 ]+')


def tokenize_name(name):
    name = name.strip().lower()

    # Keep only alpha numerics
    name = name_filter.sub('', name)

    # extract all space separated tokens from the names
    return set([w for w in name.split(' ')])


@rltk.remove_raw_object
class RecordAutry(rltk.Record):
    @rltk.cached_property
    def id(self):
        return self.raw_object['uri']['value']

    @rltk.cached_property
    def name(self):
        return self.raw_object['name']['value']

    @rltk.cached_property
    def name_tokens(self):
        return tokenize_name(self.raw_object['name']['value'])

    @rltk.cached_property
    def birthday(self):
        if 'byear' in self.raw_object:
            return self.raw_object['byear']['value']
        return None

    @rltk.cached_property
    def birthyear(self):
        if 'byear' in self.raw_object:
            return self.raw_object['byear']['value'][:4]
        return None


@rltk.remove_raw_object
class RecordULAN(rltk.Record):
    @rltk.cached_property
    def id(self):
        return self.raw_object['uri']['value']

    @rltk.cached_property
    def name(self):
        return self.raw_object['name']['value']

    @rltk.cached_property
    def name_tokens(self):
        return tokenize_name(self.raw_object['name']['value'])

    @rltk.cached_property
    def birthyear(self):
        return self.raw_object['byear']['value']


def block_on_name_prefix(r):
    ret = []
    for n in r.name_tokens:
        if len(n) > 2:
            ret.append(n[:2])
    return ret


def compare(r_aaa, r_ulan):
    # if birth year exists and not equal, exact not match
    if r_aaa.birthyear and r_ulan.birthyear:
        if r_aaa.birthyear != r_ulan.birthyear:
            return 0

    return rltk.hybrid_jaccard_similarity(r_aaa.name_tokens, r_ulan.name_tokens, threshold=0.67)


def output_handler(*arg):
    if arg[0]:
        r_aaa, r_ulan = arg[1], arg[2]
        print(r_aaa.name, r_ulan.name)


# time_start = time.time()
# pp = rltk.ParallelProcessor(is_pair, 8)
# pp.start()
#
# for idx, (r_aaa, r_ulan) in enumerate(rltk.get_record_pairs(ds_aaa, ds_ulan)):
#     print(idx)
#     pp.compute(r_aaa, r_ulan)
#
# pp.task_done()
# pp.join()
# time_pp = time.time() - time_start
# print('pp time:', time_pp)

if __name__ == '__main__':
    INIT_ULAN = False
    ulan_ds_adapter = rltk.RedisKeyValueAdapter('127.0.0.1', key_prefix='ulan_ds_')
    bg = rltk.TokenBlockGenerator()
    ulan_block = rltk.Block(rltk.RedisKeySetAdapter('127.0.0.1', key_prefix='ulan_block_'))

    # pre computing for ulan data
    if INIT_ULAN:
        ds_ulan = rltk.Dataset(reader=rltk.JsonLinesReader('../../datasets/museum/ulan.json'),
                               record_class=RecordULAN,
                               adapter=ulan_ds_adapter)
        b_ulan = bg.block(ds_ulan, function_=block_on_name_prefix, block=ulan_block)
        exit()

    # load ulan
    ds_ulan = rltk.Dataset(adapter=ulan_ds_adapter)
    b_ulan = ulan_block

    # load autry
    ds_autry = rltk.Dataset(reader=rltk.JsonLinesReader('../../datasets/museum/autry.json'),
                          record_class=RecordAutry)
    b_autry = bg.block(ds_autry, function_=block_on_name_prefix)
    b_autry_ulan = bg.generate(b_autry, b_ulan)

    # statistics
    pairwise_len = sum(1 for _ in b_autry_ulan.pairwise(ds_autry.id, ds_ulan.id))
    ulan_len = sum(1 for _ in ds_ulan)
    autry_len = sum(1 for _ in ds_autry)
    print('pairwise comparison:', pairwise_len, 'ratio: {}%'.format(pairwise_len / (ulan_len * autry_len) * 100))

    dup = {}
    for _, aid, uid in b_autry_ulan.pairwise(ds_autry.id, ds_ulan.id):
        k = '{}|{}'.format(aid, uid)
        if k not in dup:
            dup[k] = 0
        dup[k] += 1

    import operator, functools
    total = functools.reduce(operator.add, dup.values())
    print('duplicate ratio:', total / len(dup))

    # start
    print('start pairwise comparison...')
    match = {}
    threshold = 0.67
    time_start = time.time()
    for idx, (r_autry, r_ulan) in enumerate(rltk.get_record_pairs(ds_autry, ds_ulan, block=b_autry_ulan)):
        if idx % 10000 == 0:
            print('\r', idx, end='')

        score = compare(r_autry, r_ulan)
        if score > threshold:
            prev = match.get(r_autry.id, [0, 'dummy ulan id'])
            if score > prev[0]:
                match[r_autry.id] = [score, r_ulan.id]

    time_normal = time.time() - time_start
    print('\r', end='')
    print('normal time:', time_normal / 60)
    print(len(match))
    print(match)
