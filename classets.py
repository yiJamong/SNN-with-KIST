import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.utils.data as data

from torchvision.datasets.vision import VisionDataset

from bindsnet.learning import PostPre
from bindsnet.network import Network
from bindsnet.network.nodes import Input, LIFNodes, DiehlAndCookNodes, AdaptiveLIFNodes
from bindsnet.network.topology import Connection, LocalConnection
from bindsnet.encoding import Encoder, NullEncoder, PoissonEncoder

import os
from typing import Any, Callable, Dict, IO, List, Optional, Tuple, Union, Sequence, Iterable

class ECG(VisionDataset):
    
    @property
    def train_labels(self):
        warnings.warn("train_labels has been renamed targets")
        return self.targets

    @property
    def test_labels(self):
        warnings.warn("test_labels has been renamed targets")
        return self.targets

    @property
    def train_data(self):
        warnings.warn("train_data has been renamed data")
        return self.data

    @property
    def test_data(self):
        warnings.warn("test_data has been renamed data")
        return self.data

    def __init__(
            self,
            root: str,
            data_type: str,
            TR: str,
            TE: str,
            train: bool = True,
            transform: Optional[Callable] = None,
            target_transform: Optional[Callable] = None,
            download: bool = False,
    ) -> None:
        super(ECG, self).__init__(root, transform=transform,
                                    target_transform=target_transform)
        self.train = train  # training set or test set
        self.training_file = root+'/'+data_type+'/'+TR
        self.test_file = root+'/'+data_type+'/'+TE

        if download:
            pass

        if not self._check_exists():
            raise RuntimeError('Dataset not found.' +
                               ' You can use download=True to download it')
        if self.train:
            data_file = self.training_file
        else:
            data_file = self.test_file

        self.data, self.targets = torch.load(data_file)
        #self.data = list(self.data)
        #self.targets = list(self.targets)

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        """
        Args:
            index (int): Index

        Returns:
            tuple: (image, target) where target is index of the target class.
        """
        img, target = self.data[index], int(self.targets[index])

        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def __len__(self) -> int:
        return len(self.data)

    def _check_exists(self) -> bool:
        return (os.path.exists(self.training_file) and os.path.exists(self.test_file))

class TorchvisionDatasetWrapper(ECG):
    def __init__(
        self,
        image_encoder: Optional[Encoder] = None,
        label_encoder: Optional[Encoder] = None,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.args = args
        self.kwargs = kwargs

        # Allow the passthrough of None, but change to NullEncoder
        if image_encoder is None:
            image_encoder = NullEncoder()

        if label_encoder is None:
            label_encoder = NullEncoder()

        self.image_encoder = image_encoder
        self.label_encoder = label_encoder

    def __getitem__(self, ind: int) -> Dict[str, torch.Tensor]:
        image, label = super().__getitem__(ind)

        output = {
            "image": image,
            "label": label,
            "encoded_image": self.image_encoder(image),
            "encoded_label": self.label_encoder(label),
        }

        return output

    def __len__(self):
        return super().__len__()

class Class_ECG(data.Dataset):
    training_file = './training_fft_1r.pt'
    test_file = './test_fft_1r.pt'
    classes = ['0 - zero', '1 - one', '2 - two', '3 - three', '4 - four',]
            # '5 - five']
    
    def __init__(
            self,
            root: str,
            train: bool = True,
            transform: Optional[Callable] = None,
    ) -> None:
        super(ECG, self).__init__()
        self.train = train  # training set or test set
        self.root = root
        self.transform = transform
        
        if self.train:
            data_file = self.training_file
        else:
            data_file = self.test_file
        self.data, self.targets = torch.load(os.path.join(self.root, data_file))

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        datum, target = self.data[index], int(self.targets[index])

        if self.transform is not None:
            datum = self.transform(datum)
        return datum, target

    def __len__(self) -> int:
        return len(self.data)

    def _check_exists(self) -> bool:
        return (os.path.exists(os.path.join(self.root,
                                            self.training_file)) and
                os.path.exists(os.path.join(self.root,
                                            self.test_file)))

class reservoir(Network):
    def __init__(
        self,
        n_inpt: int,
        w_inpt: [float],
        n_liquid: int,
        w_liquid: [float],
        n_neurons: int = 512,
        exc: float = 22.5,
        inh: float = 17.5,
        dt: float = 1.0,
        nu: Optional[Union[float, Sequence[float]]] = (1e-4, 1e-2),
        reduction: Optional[callable] = None,
        wmin: float = 0.0,
        wmax: float = 1.0,
        norm: float = 51.2,
        theta_plus: float = 0.05,
        tc_theta_decay: float = 1e7,
        inpt_shape: Optional[Iterable[int]] = None,
    ) -> None:
        # language=rst
        """
        Constructor for class ``DiehlAndCook2015``.
        :param n_inpt: Number of input neurons. Matches the 1D size of the input data.
        :param n_neurons: Number of excitatory, inhibitory neurons.
        :param exc: Strength of synapse weights from excitatory to inhibitory layer.
        :param inh: Strength of synapse weights from inhibitory to excitatory layer.
        :param dt: Simulation time step.
        :param nu: Single or pair of learning rates for pre- and post-synaptic events,
            respectively.
        :param reduction: Method for reducing parameter updates along the minibatch
            dimension.
        :param wmin: Minimum allowed weight on input to excitatory synapses.
        :param wmax: Maximum allowed weight on input to excitatory synapses.
        :param norm: Input to excitatory layer connection weights normalization
            constant.
        :param theta_plus: On-spike increment of ``DiehlAndCookNodes`` membrane
            threshold potential.
        :param tc_theta_decay: Time constant of ``DiehlAndCookNodes`` threshold
            potential decay.
        :param inpt_shape: The dimensionality of the input layer.
        """
        super().__init__(dt=dt)

        self.n_inpt = n_inpt
        self.w_inpt = w_inpt
        self.n_liquid = n_liquid
        self.w_liquid = w_liquid
        self.inpt_shape = inpt_shape
        self.n_neurons = n_neurons
        self.exc = exc
        self.inh = inh
        self.dt = dt

        # Layers
        input_layer = Input(
            n=self.n_inpt, 
            shape=self.inpt_shape,
            #traces=True, tc_trace=20.0
        )
        liquid_layer = LIFNodes(
            n_liquid, 
            thresh=-52.0,
            traces=True, tc_trace=20.0
            )
        exc_layer = DiehlAndCookNodes(
            n=self.n_neurons,
            traces=True,
            rest=-65.0,
            reset=-60.0,
            thresh=-52.0,
            refrac=5,
            tc_decay=100.0,
            tc_trace=20.0,
            theta_plus=theta_plus,
            tc_theta_decay=tc_theta_decay,
        )
        inh_layer = LIFNodes(
            n=self.n_neurons,
            traces=False,
            rest=-60.0,
            reset=-45.0,
            thresh=-40.0,
            tc_decay=10.0,
            refrac=2,
            tc_trace=20.0,
        )

        # Connections
        input_liquid_conn = Connection(
            source=input_layer, 
            target=liquid_layer, 
            w=self.w_inpt,
        )
        liquid_liquid_conn = Connection(
            source=liquid_layer, 
            target=liquid_layer, 
            w=self.w_liquid,
        )
        w = 0.3 * torch.rand(self.n_liquid, self.n_neurons)
        liquid_exc_conn = Connection(
            source=liquid_layer,
            target=exc_layer,
            w=w,
            update_rule=PostPre,
            nu=nu,
            reduction=reduction,
            wmin=wmin,
            wmax=wmax,
            norm=norm,
        )
        w = self.exc * torch.diag(torch.ones(self.n_neurons))
        exc_inh_conn = Connection(
            source=exc_layer, target=inh_layer, w=w, wmin=0, wmax=self.exc
        )
        w = -self.inh * (
            torch.ones(self.n_neurons, self.n_neurons)
            - torch.diag(torch.ones(self.n_neurons))
        )
        inh_exc_conn = Connection(
            source=inh_layer, target=exc_layer, w=w, wmin=-self.inh, wmax=0
        )

        # Add to network
        self.add_layer(input_layer, name="I")
        self.add_layer(liquid_layer, name="X")
        self.add_layer(exc_layer, name="Ae")
        self.add_layer(inh_layer, name="Ai")
        self.add_connection(input_liquid_conn, source="I", target="X")
        self.add_connection(liquid_liquid_conn, source="X", target="X")        
        self.add_connection(liquid_exc_conn, source="X", target="Ae")
        self.add_connection(exc_inh_conn, source="Ae", target="Ai")
        self.add_connection(inh_exc_conn, source="Ai", target="Ae")

class customECG(VisionDataset):
    """`MNIST <http://yann.lecun.com/exdb/mnist/>`_ Dataset.

    Args:
        root (string): Root directory of dataset where ``MNIST/processed/training.pt``
            and  ``MNIST/processed/test.pt`` exist.
        train (bool, optional): If True, creates dataset from ``training.pt``,
            otherwise from ``test.pt``.
        download (bool, optional): If true, downloads the dataset from the internet and
            puts it in root directory. If dataset is already downloaded, it is not
            downloaded again.
        transform (callable, optional): A function/transform that  takes in an PIL image
            and returns a transformed version. E.g, ``transforms.RandomCrop``
        target_transform (callable, optional): A function/transform that takes in the
            target and transforms it.
    """

    training_file = 'training_fft_1m.pt'
    test_file = 'test_fft_1m.pt'
    classes = ['0 - zero', '1 - one', '2 - two', '3 - three', '4 - four']

    @property
    def train_labels(self):
        warnings.warn("train_labels has been renamed targets")
        return self.targets

    @property
    def test_labels(self):
        warnings.warn("test_labels has been renamed targets")
        return self.targets

    @property
    def train_data(self):
        warnings.warn("train_data has been renamed data")
        return self.data

    @property
    def test_data(self):
        warnings.warn("test_data has been renamed data")
        return self.data

    def __init__(
            self,
            root: str,
            train: bool = True,
            transform: Optional[Callable] = None,
            target_transform: Optional[Callable] = None,
            download: bool = False,
    ) -> None:
        super(customECG, self).__init__(root, transform=transform,
                                    target_transform=target_transform)
        self.train = train  # training set or test set

        if self.train:
            data_file = self.training_file
        else:
            data_file = self.test_file

        self.data, self.targets = torch.load(os.path.join(self.processed_folder, data_file))

    def __getitem__(self, index: int) -> Tuple[Any, Any]:
        """
        Args:
            index (int): Index

        Returns:
            tuple: (image, target) where target is index of the target class.
        """
        img, target = self.data[index], int(self.targets[index])

        # doing this so that it is consistent with all other datasets
        # to return a PIL Image
        #img = Image.fromarray(img.numpy(), mode='L')

        if self.transform is not None:
            img = self.transform(img)
        #print(img.dtype)
        if self.target_transform is not None:
            target = self.target_transform(target)

        return img, target

    def __len__(self) -> int:
        return len(self.data)

    @property
    def raw_folder(self) -> str:
        return os.path.join(self.root, self.__class__.__name__, 'raw')

    @property
    def processed_folder(self) -> str:
        return os.path.join(self.root, self.__class__.__name__, 'processed')

    @property
    def class_to_idx(self) -> Dict[str, int]:
        return {_class: i for i, _class in enumerate(self.classes)}

    def extra_repr(self) -> str:
        return "Split: {}".format("Train" if self.train is True else "Test")


class Outlayer(data.Dataset):
    def __init__(self, x_tensor, y_tensor):
        super(Outlayer, self).__init__()

        self.data = x_tensor
        self.targets = y_tensor

    def __getitem__(self, index: int) -> Tuple[Any,Any]:
        datum, target = self.data[index], int(self.targets[index])

        return datum, target
    def __len__(self):
        return len(self.data)

class CNN(torch.nn.Module):

    def __init__(self, input_size, num_classes):
        super(CNN, self).__init__()
        self.input_size = input_size
        self.num_classes = num_classes
        self.keep_prob = 0.5

        # L1 ImgIn shape=(?, 28, 28, 1)
        #    Conv     -> (?, 28, 28, 32)
        #    Pool     -> (?, 14, 14, 32)
        self.layer1 = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2, stride=2))
        # L2 ImgIn shape=(?, 14, 14, 32)
        #    Conv      ->(?, 14, 14, 64)
        #    Pool      ->(?, 7, 7, 64)
        self.layer2 = nn.Sequential(
            nn.Conv1d(32, 64, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2, stride=2))
        # L3 ImgIn shape=(?, 7, 7, 64)
        #    Conv      ->(?, 7, 7, 128)
        #    Pool      ->(?, 4, 4, 128)
        self.layer3 = nn.Sequential(
            nn.Conv1d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=2, stride=2))

        # L4 FC 4x4x128 inputs -> 625 outputs
        self.fc1 = nn.Linear(self.input_size // 8 * 128, 625, bias=True)
        nn.init.xavier_uniform_(self.fc1.weight)
        self.layer4 = nn.Sequential(
            self.fc1,
            nn.ReLU(),
            nn.Dropout(p=1 - self.keep_prob))
        # L5 Final FC 625 inputs -> 10 outputs
        self.fc2 = nn.Linear(625, self.num_classes, bias=True)
        nn.init.xavier_uniform_(self.fc2.weight)

    def forward(self, x):
        out = self.layer1(x.unsqueeze(dim=0).unsqueeze(dim=0))
        out = self.layer2(out)
        out = self.layer3(out)
        out = out.view(out.size(0), -1)   # Flatten them for FC
        out = self.layer4(out)
        out = self.fc2(out)
        return out

class NN(nn.Module):
    def __init__(self, input_size, num_classes):
        super(NN, self).__init__()
        h = int(input_size/2)
        #self.linear_1 = nn.Linear(input_size, num_classes)
        self.linear_1 = nn.Linear(input_size, h)
        self.linear_2 = nn.Linear(h, num_classes)

    def forward(self, x):
        out = torch.sigmoid(self.linear_1(x.float().view(-1)))
        out = self.linear_2(out)#torch.sigmoid(self.linear_2(out))
        return out

class ANN(nn.Module):
    def __init__(self, input_size, num_classes):
        super(ANN, self).__init__()
        self.fc1 = nn.Linear(input_size, 512)
        self.fc2 = nn.Linear(512, 256)
        self.fc3 = nn.Linear(256, 128)
        self.fc4 = nn.Linear(128, 64)
        self.fc5 = nn.Linear(64, 32)
        self.fc6 = nn.Linear(32, num_classes)

    def forward(self, x):
        x = x.float()
        h1 = F.relu(self.fc1(x.view(1,-1)))
        h2 = F.relu(self.fc2(h1))
        h3 = F.relu(self.fc3(h2))
        h4 = F.relu(self.fc4(h3))
        h5 = F.relu(self.fc5(h4))
        h6 = self.fc6(h5)
        return h6 #F.log_softmax(h6, dim=1)
