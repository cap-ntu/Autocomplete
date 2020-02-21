import os
import time
from abc import abstractmethod

import numpy as np
import torch

from autocomplete.lib.file import create_directory_if_not_exists


def timestamp():
    return int(time.time())


class Metrics:
 
    def __init__(self):
        self.is_train = True

    def train(self):
        self.is_train = True

    def eval(self):
        self.is_train = False

    @abstractmethod
    def drop_state(self):
        pass

    @abstractmethod
    def report(self, *values):
        pass

    @abstractmethod
    def get_current_value(self, should_print=False):
        pass

    def decrease_hits(self, number):
        print('Decrease hits not implemented!!!')


class LossMetrics(Metrics):
    def __init__(self):
        super().__init__()
        self.total_loss = None
        self.total_count = 0

    def drop_state(self):
        self.total_loss = None
        self.total_count = 0

    def report(self, loss):
        if self.total_loss is None:
            self.total_loss = loss
        else:
            self.total_loss += loss

        self.total_count += 1

    def get_current_value(self, should_print=False):
        loss_value = self.total_loss.item() / self.total_count
        if should_print:
            print('Current loss: {}'.format(loss_value))
        return loss_value


class BaseAccuracyMetrics(Metrics):
    def __init__(self):
        super().__init__()
        self.hits = 0
        self.misses = 0
        self.reported = 0

    def drop_state(self):
        self.hits = 0
        self.misses = 0
        self.reported = 0

    def report(self, prediction_target):
        prediction, target = prediction_target
        self.reported += 1

        current_misses = torch.nonzero(prediction - target)
        if len(current_misses.size()) == 0:
            current_misses = 0
        else:
            current_misses = current_misses.size()[0]
        current_hits = target.view(-1).size()[0] - current_misses

        self.hits += current_hits
        self.misses += current_misses

    def get_current_value(self, should_print=False):
        if self.hits + self.misses == 0:
            return 0
        value = float(self.hits) / (self.hits + self.misses)

        if should_print:
            print('Current accuracy: {}'.format(value))

        return value


class MaxPredictionWrapper(Metrics):
    def __init__(self, base: Metrics, dim=2):
        super().__init__()
        self.base = base
        self.dim = dim

    def drop_state(self):
        self.base.drop_state()

    def report(self, prediction_target):
        prediction, target = prediction_target
        _, predicted = torch.max(prediction, dim=self.dim)
        self.base.report((predicted, target))

    def get_current_value(self, should_print=False):
        return self.base.get_current_value(should_print=should_print)

    def decrease_hits(self, number):
        self.base.decrease_hits(number)


class MaxPredictionAccuracyMetrics(BaseAccuracyMetrics):
    def __init__(self, dim=2):
        super().__init__()
        self.dim = dim

    def report(self, prediction_target):
        prediction, target = prediction_target
        _, predicted = torch.max(prediction, dim=self.dim)
        super().report((predicted, target))


class IndexedAccuracyMetrics(Metrics):
    def __init__(self, label):
        super().__init__()
        self.label = label
        self.metrics = BaseAccuracyMetrics()

    def drop_state(self):
        self.metrics.drop_state()

    def report(self, predicted, target, indexes):
        predicted = torch.index_select(predicted, 0, indexes)
        target = torch.index_select(target, 0, indexes)
        self.metrics.report((predicted, target))

    def get_current_value(self, should_print=False):
        value = self.metrics.get_current_value(should_print=False)

        if should_print:
            print('{}: {}'.format(self.label, value))

        return value

    def decrease_hits(self, number):
        self.metrics.decrease_hits(number)


class ResultsSaver(Metrics):
    def __init__(self, dir_to_save):
        super().__init__()
        self.file_to_save = dir_to_save
        self.predicted = []
        self.target = []

        if not os.path.exists(self.file_to_save):
            os.makedirs(self.file_to_save)

    def drop_state(self):
        self.predicted = []
        self.target = []

    def report(self, predicted_target):
        predicted, target = predicted_target
        self.predicted.append(predicted.cpu().numpy())
        self.target.append(target.cpu().numpy())

    def get_current_value(self, should_print=False):
        predicted = np.concatenate(self.predicted, axis=0)
        target = np.concatenate(self.target, axis=0)

        t = str(timestamp())
        predicted.dump(self.file_to_save + '/predicted' + t)
        target.dump(self.file_to_save + '/target' + t)


class SequentialMetrics(Metrics):
    def __init__(self, metrics):
        super().__init__()
        self.metrics = metrics

    def drop_state(self):
        for m in self.metrics:
            m.drop_state()

    def report(self, prediction_target):
        for m in self.metrics:
            m.report(prediction_target)

    def get_current_value(self, should_print=False):
        result = None
        print('=====> =====> =====>')
        for m in self.metrics:
            cur = m.get_current_value(should_print=should_print)
            print('=====> =====> =====>')
            if result is None:
                result = cur

        return result

    def decrease_hits(self, number):
        for m in self.metrics:
            m.decrease_hits(number)


class TensorVisualizerMetrics(Metrics):
    def __init__(self, mapper=None, file='eval/temp/tensor_visualization'):
        super().__init__()
        self.mapper = mapper
        if self.mapper is None:
            self.mapper = lambda x: x
        self.file = file
        self.sum = None
        self.reported = 0

    def drop_state(self):
        pass

    def report(self, output):
        current_sum = self.mapper(output.detach())
        if self.sum is None:
            self.sum = current_sum
        else:
            self.sum = self.sum + current_sum
        self.reported += 1

    def get_current_value(self, should_print=False):
        value = self.sum / self.reported
        if self.file is None:
            return value  
        np.save(self.file, value.cpu().numpy())
        return 0 


class TensorVisualizer2DMetrics(TensorVisualizerMetrics):
    def __init__(self, dim=0, file='eval/temp/tensor_visualization2d'):
        super().__init__(
            mapper=lambda output: torch.sum(output, dim=dim).float() / output.size()[dim],
            file=file
        )

    def report(self, output):
        assert len(output.size()) == 2
        super().report(output)


class TensorVisualizer3DMetrics(TensorVisualizerMetrics):
    def __init__(self, file='eval/temp/tensor_visualization3d'):
        super().__init__(
            mapper=lambda output: output.view(-1, output.size()[-1]).sum(0) / (output.size()[0] * output.size()[1]),
            file=file
        )

    def report(self, output):
        assert len(output.size()) == 3
        super().report(output)


class FeaturesMeanVarianceMetrics(Metrics):
    def __init__(self, directory='eval/temp'):
        super().__init__()
        self.directory = directory
        create_directory_if_not_exists(self.directory)

        self.sum = None
        self.squares_sum = None
        self.reported = 0

    def drop_state(self):
        self.sum = None
        self.squares_sum = None
        self.reported = 0

    def report(self, value):
        value = value.view(-1, value.size()[-1])
        assert len(value.size()) == 2
        batch_size = value.size()[0]

        c_sum = torch.sum(value.detach(), dim=0) / batch_size
        c_squared_sum = torch.sum(value.detach() ** 2, dim=0) / batch_size

        if self.sum is None:
            self.sum = c_sum
            self.squares_sum = c_squared_sum
        else:
            self.sum += c_sum
            self.squares_sum += c_squared_sum
        self.reported += 1

    def get_current_value(self, should_print=False):
        mean = self.sum / self.reported
        variance = (self.squares_sum / self.reported) - (self.sum / self.reported) ** 2

        np.save(os.path.join(self.directory, 'mean'), mean.cpu().numpy())
        np.save(os.path.join(self.directory, 'variance'), variance.cpu().numpy())


class TopKWrapper(Metrics):
    def __init__(self, base: Metrics, k=5, dim=2):
        super().__init__()
        self.base = base
        self.k = k
        self.dim = dim

    def drop_state(self):
        self.base.drop_state()

    def report(self, predicted_target):
        predicted, target = predicted_target
        with torch.no_grad():
            _, top_pred = predicted.topk(self.k, self.dim, True, True)
            self.base.report((top_pred, target))

    def get_current_value(self, should_print=False):
        self.base.get_current_value(should_print=True)


class TopKAccuracy(Metrics):
    def __init__(self, k):
        super().__init__()
        self.k = k
        self.hits = np.zeros(self.k)
        self.total = np.zeros(self.k)

    def drop_state(self):
        self.hits = np.zeros(self.k)
        self.total = np.zeros(self.k)

    def report(self, prediction_target):
        topk_prediction, target = prediction_target
        topk_prediction = topk_prediction.view(-1, topk_prediction.size()[-1])
        target = target.view(-1)

        batch_total = target.size()[0]
        correct = topk_prediction.eq(target.unsqueeze(1).expand_as(topk_prediction))
        for tk in range(self.k):
            cur_hits = correct[:, :tk + 1]
            self.hits[tk] += cur_hits.sum()
            self.total[tk] += batch_total

    def get_current_value(self, should_print=False):
        res = self.hits / self.total
        if should_print:
            print(res)

        return res[0] 

