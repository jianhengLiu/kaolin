# Copyright (c) 2021 NVIDIA CORPORATION & AFFILIATES.
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest
import torch
from itertools import combinations, chain

from kaolin.rep import Spc
from kaolin.ops.spc import bits_to_uint8

def _test_func(octrees, lengths, another_arg=None, **kwargs):
    remaining_kwargs = kwargs.keys() - Spc.KEYS
    if len(remaining_kwargs) > 0:
        raise TypeError("_test_func got an unexpected keyword argument "
                        f"{list(remaining_kwargs)[0]}")

class TestSpc:
    @pytest.fixture(autouse=True)
    def octrees(self):
        bits_t = torch.tensor([
            [0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 1, 1, 0], [0, 0, 1, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 0],

            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 1, 1, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1],  [0, 1, 0, 1, 0, 1, 0, 1]],
            device='cuda', dtype=torch.float)
        return bits_to_uint8(torch.flip(bits_t, dims=(-1,)))

    @pytest.fixture(autouse=True)
    def lengths(self):
        return torch.tensor([6, 5], dtype=torch.int)

    @pytest.fixture(autouse=True)
    def expected_max_level(self):
        return 3

    @pytest.fixture(autouse=True)
    def expected_pyramids(self):
        return torch.tensor(
            [[[1, 2, 3, 3, 0], [0, 1, 3, 6, 9]],
             [[1, 1, 3, 13, 0], [0, 1, 2, 5, 18]]], dtype=torch.int32)

    @pytest.fixture(autouse=True)
    def expected_exsum(self):
        return torch.tensor(
            [0, 2, 4, 5, 6, 7, 8, 0, 1, 4, 5, 13, 17],
            dtype=torch.int32, device='cuda')

    @pytest.fixture(autouse=True)
    def expected_point_hierarchies(self):
        return torch.tensor([
            [0, 0, 0],
            [0, 0, 0], [1, 0, 0],
            [0, 0, 1], [0, 1, 0], [3, 0, 1],
            [1, 1, 3], [1, 3, 1], [6, 1, 3],

            [0, 0, 0],
            [1, 1, 1],
            [3, 2, 2], [3, 2, 3], [3, 3, 2],
            [7, 4, 5], [6, 4, 6], [6, 4, 7], [6, 5, 6], [6, 5, 7], [7, 4, 6], \
                [7, 4, 7], [7, 5, 6], [7, 5, 7], [6, 6, 4], [6, 7, 4], \
                [7, 6, 4], [7, 7, 4]
            ], device='cuda', dtype=torch.int16)

    def test_non_init_private_attr(self, octrees, lengths):
        """Check that private placeholder attributes
        are not initialized after constructor"""
        spc = Spc(octrees, lengths)
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)
        assert spc._max_level is None
        assert spc._pyramids is None
        assert spc._exsum is None
        assert spc._point_hierarchies is None

    def test_init_private_attr(self, octrees, lengths, expected_max_level,
                               expected_pyramids, expected_exsum, expected_point_hierarchies):
        """Check that private placeholder attributes
        are initialized if specified at constructor"""
        spc = Spc(octrees, lengths, expected_max_level, expected_pyramids,
                  expected_exsum, expected_point_hierarchies)
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)
        assert spc._max_level == expected_max_level
        assert torch.equal(spc._pyramids, expected_pyramids)
        assert torch.equal(spc._exsum, expected_exsum)
        assert torch.equal(spc._point_hierarchies, expected_point_hierarchies)

    def test_scan_octrees_properties(self, octrees, lengths, expected_max_level,
                                     expected_pyramids, expected_exsum):
        """Check that properties generated by scan_octrees are accessible"""
        spc = Spc(octrees, lengths)
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)
        assert spc.max_level == expected_max_level
        assert torch.equal(spc.pyramids, expected_pyramids)
        assert torch.equal(spc.exsum, expected_exsum)
        # This is checking that:
        # 1) data pointer on properties is the same than on private attributes
        # 2) private attributes are not recomputed
        assert spc._pyramids.data_ptr() == spc.pyramids.data_ptr()
        assert spc._exsum.data_ptr() == spc.exsum.data_ptr()
        # _point_hierarchies is still not initialized
        assert spc._point_hierarchies is None

    def test_generate_points_properties(self, octrees, lengths,
                                        expected_point_hierarchies):
        """Check that properties generated by generate_points are accessible"""
        spc = Spc(octrees, lengths)
        assert spc._point_hierarchies is None
        assert torch.equal(spc.point_hierarchies, expected_point_hierarchies)
        # point_hierarchies, generated _max_level, _pyramids and _exsum
        # as they are dependencies
        assert spc._max_level is not None
        assert spc._pyramids is not None
        assert spc._exsum is not None

        # Check that calling point_hierarchies properties again
        # is not recomputing the private attributes
        old_pyramids_data_ptr = spc._pyramids.data_ptr()
        old_exsum_data_ptr = spc._exsum.data_ptr()
        assert spc._point_hierarchies.data_ptr() == spc.point_hierarchies.data_ptr()
        assert old_pyramids_data_ptr == spc._pyramids.data_ptr()
        assert old_exsum_data_ptr == spc._exsum.data_ptr()

    def test_from_list(self, octrees, lengths):
        octrees_list = []
        start_idx = 0
        for length in lengths:
            octrees_list.append(octrees[start_idx:start_idx + length])
            start_idx += length
        spc = Spc.from_list(octrees_list)
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)

    def test_cpu_init(self, octrees, lengths, expected_max_level,
                      expected_pyramids, expected_exsum, expected_point_hierarchies):
        octrees = octrees.cpu()
        expected_exsum = expected_exsum.cpu()
        expected_point_hierarchies = expected_point_hierarchies.cpu()
        spc = Spc(octrees, lengths, expected_max_level, expected_pyramids,
                  expected_exsum, expected_point_hierarchies)
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)
        assert spc.max_level == expected_max_level
        assert torch.equal(spc.pyramids, expected_pyramids)
        assert torch.equal(spc.exsum, expected_exsum)
        assert torch.equal(spc.point_hierarchies, expected_point_hierarchies)

    @pytest.mark.parametrize('using_to', [False, True])
    def test_to_cpu(self, using_to, octrees, lengths, expected_max_level,
                    expected_pyramids, expected_exsum, expected_point_hierarchies):
        spc = Spc(octrees, lengths, expected_max_level, expected_pyramids,
                  expected_exsum, expected_point_hierarchies)
        if using_to:
            spc = spc.to('cpu')
        else:
            spc = spc.cpu()
        assert torch.equal(spc.octrees, octrees.cpu())
        assert torch.equal(spc.lengths, lengths)
        assert spc.max_level == expected_max_level
        assert torch.equal(spc.pyramids, expected_pyramids)
        assert torch.equal(spc.exsum, expected_exsum.cpu())
        assert torch.equal(spc.point_hierarchies, expected_point_hierarchies.cpu())

    @pytest.mark.parametrize('using_to', [False, True])
    def test_to_cuda(self, using_to, octrees, lengths, expected_max_level,
                     expected_pyramids, expected_exsum, expected_point_hierarchies):
        spc = Spc(octrees.cpu(), lengths, expected_max_level, expected_pyramids,
                  expected_exsum.cpu(), expected_point_hierarchies.cpu())
        if using_to:
            spc = spc.to('cuda')
        else:
            spc = spc.cuda()
        assert torch.equal(spc.octrees, octrees)
        assert torch.equal(spc.lengths, lengths)
        assert spc.max_level == expected_max_level
        assert torch.equal(spc.pyramids, expected_pyramids)
        assert torch.equal(spc.exsum, expected_exsum)
        assert torch.equal(spc.point_hierarchies, expected_point_hierarchies)

    def test_to_dict_default(self, octrees, lengths, expected_max_level,
                             expected_pyramids, expected_exsum, expected_point_hierarchies):
        spc = Spc(octrees, lengths)
        d = spc.to_dict()
        assert d.keys() == {'octrees', 'lengths', 'max_level', 'pyramids',
                            'exsum', 'point_hierarchies'}
        assert torch.equal(d['octrees'], octrees)
        assert torch.equal(d['lengths'], lengths)
        assert d['max_level'] == expected_max_level
        assert torch.equal(d['pyramids'], expected_pyramids)
        assert torch.equal(d['exsum'], expected_exsum)
        assert torch.equal(d['point_hierarchies'], expected_point_hierarchies)

    @pytest.mark.parametrize('keys', list(chain(*[combinations(
        ['octrees', 'lengths', 'max_level', 'pyramids', 'exsum', 'point_hierarchies'],
        i) for i in range(1, 7)])))
    def test_to_dict_with_keys(self, keys, octrees, lengths,
                               expected_max_level, expected_pyramids,
                               expected_exsum, expected_point_hierarchies):
        keys = set(keys)
        spc = Spc(octrees, lengths)
        d = spc.to_dict(keys)
        assert d.keys() == keys
        if 'octrees' in keys:
            assert torch.equal(d['octrees'], octrees)
        if 'lengths' in keys:
            assert torch.equal(d['lengths'], lengths)
        if 'max_level' in keys:
            assert d['max_level'] == expected_max_level
        if 'pyramids' in keys:
            assert torch.equal(d['pyramids'], expected_pyramids)
        if 'exsum' in keys:
            assert torch.equal(d['exsum'], expected_exsum)
        if 'point_hierarchies' in keys:
            assert torch.equal(d['point_hierarchies'], expected_point_hierarchies)

    def test_to_dict_kwargs(self, octrees, lengths):
        spc = Spc(octrees, lengths)
        _test_func(**spc.to_dict(), another_arg=1)

    def test_typo_to_dict_kwargs(self, octrees, lengths):
        spc = Spc(octrees, lengths)
        with pytest.raises(TypeError,
                           match="_test_func got an unexpected keyword argument anotherarg"):
            #typo on purpose
            _test_func(**spc.to_dict(), anotherarg=1)
