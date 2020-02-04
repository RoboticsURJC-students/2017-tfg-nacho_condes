import argparse
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
#import seaborn as sns
import yaml
# from utils import TO_MS
from PIL import Image
from Net.detection_network import DetectionNetwork
from Camera.ROSCam import ROSCam
from os import listdir, path, makedirs, chdir
from cprint import cprint
#sns.set()

# Change the working directory in order to have access to the modules
# abspath = path.abspath(__file__)
# dname = path.dirname(abspath)
# chdir(dname)


FILENAME_FORMAT = '%Y%m%d %H%M%S'
TO_MS = np.vectorize(lambda x: x.seconds * 1000.0 + x.microseconds / 1000.0) # Auxiliary vectorized function


class FollowPersonBenchmarker:
    ''' Writer for a full-set benchmark using a certain configuration. '''
    def __init__(self, logdir):
        self.logdir = logdir
        self.description = None

    def write_benchmark(self, times_list, rosbag_file,
                        pdet_model, fenc_model,
                        t_pers_det, t_face_det, t_face_enc, ttfi,
                        display_images, write_iters=True, dirname=None):
        ''' Write the metrics to the output file. '''

        benchmark = {}
        summary = {}
        summary['1.- Configuration'] = {
            '1.- Networks': {
                '1.- PersonDetectionModel': pdet_model,
                # '2.- FaceDetectionModel':   fdet_model,
                '2.- FaceEncodingModel':    fenc_model,
            },
            '2.- RosbagFile': rosbag_file,
            '3.- DisplayImages': display_images,
        }
        summary['2.- LoadTimes'] = {
            '1.- PersonDetectionNetworkLoad': float(TO_MS(t_pers_det)),
            '2.- FaceDetectionNetworkLoad':   float(TO_MS(t_face_det)),
            '3.- FaceEncodingNetworkLoad':    float(TO_MS(t_face_enc)),
            '4.- TTFI':                       float(TO_MS(ttfi)),
        }

        # Process the measured times
        times_raw = np.array(times_list)
        # Split dropping the first (slower) inference
        iters_raw = times_raw[1:, 0]
        total_iters = TO_MS(iters_raw)

        pdets_raw = np.array(list(times_raw[1:, 1]))
        total_pdets = pdets_raw.copy()
        total_pdets[:, 0] = TO_MS(total_pdets[:, 0])

        fdets_raw = np.array(list(times_raw[1:, 2]))
        total_fdets = fdets_raw.copy()
        total_fdets[:, 0] = TO_MS(fdets_raw[:, 0])

        fencs_raw = np.array(list(times_raw[1:, 3]))
        total_fencs = fencs_raw.copy()
        total_fencs[:, 0] = TO_MS(total_fencs[:, 0])
        total_fencs_flt = total_fencs[total_fencs[:, 1] > 0]  # Just times belonging to a face filtering
        # total_fencs_flt = list(filter(lambda x: x[1] > 0, total_fencs))

        if display_images:
            disps_raw = times_raw[1:, 4]
            total_disps = TO_MS(disps_raw)

        summary['3.- Stats'] = {
            '1.- PersonDetection': {
                '1.- Mean': float(total_pdets.mean()),
                '2.- Std':  float(total_pdets.std()),
            },
            '2.- FaceDetection': {
                '1.- Mean': float(total_fdets.mean()),
                '2.- Std':  float(total_fdets.std()),
            },
            '3.- FaceEncoding': {
                '1.- Mean': float(total_fencs_flt.mean()),
                '2.- Std':  float(total_fencs_flt.std()),
            }
        }
        benchmark['1.- Summary'] = summary

        if write_iters:
            iterations = []
            for it_time, pdet, fdet, fenc in zip(total_iters, total_pdets, total_fdets, total_fencs):
                iteration = {}
                # Persons detection
                persons_detection = {}
                n_persons = len(pdet)
                persons_detection['1.- NumDetections'] = int(n_persons)
                if n_persons == 0:
                    continue
                persons_detection['2.- TotalTime'] = float(pdet.sum())
                # Faces detection
                faces_detection = {}
                n_faces = fdet[1]
                faces_detection['1.- NumDetections'] = int(n_faces)
                if n_faces == 0:
                    continue
                faces_detection['2.- TotalTime'] = float(fdet.sum())
                # Faces encoding
                faces_encoding = {}
                n_faces = fenc[1]
                faces_encoding['1.- NumDetections'] = int(n_faces)
                if n_faces == 0:
                    continue
                faces_encoding['2.- TotalTime'] = float(fenc.sum())

                iteration = {
                    '1.- PersonsDetection':   persons_detection,
                    '2.- FacesDetection':     faces_detection,
                    '3.- FacesEncoding':      faces_encoding,
                    '4.- TotalIterationTime': float(it_time),
                }
                iterations.append(iteration)

            benchmark['2.- Iterations'] = iterations

        if dirname is None:
            dirname = datetime.now().strftime(FILENAME_FORMAT)

        dirname = path.join(self.logdir, dirname)
        if not path.exists(dirname):
            makedirs(dirname)
        benchmark_name = path.join(dirname, 'benchmark.yml')

        # Dump
        with open(benchmark_name, 'w') as f:
            yaml.dump(benchmark, f)

        print(f'Saved on {benchmark_name}')
        # Graphs
        #   Total iteration time
        fig, ax = plt.subplots()
        ax.plot(total_iters)
        ax.set_title('Total iteration time')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Time (ms)')
        figname = path.join(dirname, 'iterations.png')
        fig.savefig(figname)

        #   Person detection time
        fig, ax = plt.subplots()
        ax.plot(total_pdets[:, 0])
        ax.set_title('Person detection time')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Time (ms)')
        figname = path.join(dirname, 'person_detections.png')
        fig.savefig(figname)

        #   Face detection time
        fig, ax = plt.subplots()
        ax.plot(total_fdets[:, 0])
        ax.set_title('Face detection time')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Time (ms)')
        figname = path.join(dirname, 'face_detections.png')
        fig.savefig(figname)

        #   Face encoding time
        fig, ax = plt.subplots()
        ax.plot(total_fencs[:, 0])
        ax.set_title('Face encoding time')
        ax.set_xlabel('Iteration')
        ax.set_ylabel('Time (ms)')
        figname = path.join(dirname, 'face_encoding.png')
        fig.savefig(figname)


class SingleModelBenchmarker:
    ''' Writer for a single model benchmark using. '''
    def __init__(self, save_in):
        self.save_in = save_in

    def write_benchmark(self, total_times, model_name, rosbag_file, arch, write_iters=True):
        # Convert the lapse measurements to milliseconds
        total_ms = np.array(total_times)
        total_ms[:, 0] = TO_MS(total_ms[:, 0])
        # Filter the non-empty inferences
        nonempty = total_ms[total_ms[:, 1] > 0]

        dic = {}
        # Metadata
        dic['1.- Meta'] = {
            '1.- ModelName': model_name,
            '2.- ROSBag': rosbag_file,
            '3.- Architecture': arch,
        }
        # Stats
        stats_total = {
            'Mean': f'{total_ms[:, 0].mean():.4f} ms',
            'Std':  f'{total_ms[:, 0].std():.4f} ms',
        }

        stats_nonempty = {
            'Mean': f'{nonempty[:, 0].mean():.4f} ms',
            'Std':  f'{nonempty[:, 0].std():.4f} ms',
        }

        dic['2.- Stats'] = {
            '1.- Total': stats_total,
            '2.- NonEmpty': stats_nonempty,
        }

        if write_iters:
            iters = {}
            for idx, iteration in enumerate(total_ms):
                iters[idx] = {
                    'InferenceTime': f'{iteration[0]:.4f} ms',
                    'NumDetections': iteration[1]
                }
            dic['3.- Iterations'] = iters

        # Finally, dump the results into the requested file.
        with open(self.save_in, 'w') as f:
            yaml.dump(dic, f)
        cprint.ok(f'Benchmark written in {self.save_in}!')




if __name__ == '__main__':
    description = ''' If this script is called, it will perform inferences using
    a provided model on a test rosbag, and will store the results into a YML file. '''

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('pb_file', type=str, help='.pb file containing the frozen graph to test')
    parser.add_argument('arch', type=str, help='Detection architecture of the provided network')
    parser.add_argument('input_width', type=int, help='Width of the network input')
    parser.add_argument('input_height', type=int, help='Height of the network input')
    parser.add_argument('rosbag_file', type=str, help='ROSBag to perform the test on')
    parser.add_argument('save_in', type=str, help='File in which write the output result')
    # Parse the args
    args = parser.parse_args()

    # print('\n' * 10, listdir('.'), '\n' * 20)
    pb_file = args.pb_file
    rosbag_file = args.rosbag_file

    # Check the existance of the files
    if not path.isfile(pb_file):
        cprint.fatal(f'Error: the provided frozen graph {pb_file} does not exist', interrupt=True)
    if not path.isfile(rosbag_file):
        cprint.fatal(f'Error: the provided ROSBag {rosbag_file} does not exist', interrupt=True)


    save_in = args.save_in
    arch = args.arch
    input_w, input_h = args.input_width, args.input_height

    # Create the ROSCam to open the ROSBag
    topics = {'RGB': '/camera/rgb/image_raw',
              'Depth': '/camera/depth_registered/image_raw'}
    cam = ROSCam(topics, rosbag_file)

    # Load the model into a network object to perform inferences
    input_shape = (input_h, input_w, 3)
    net = DetectionNetwork(arch, input_shape, pb_file)

    total_times = []
    # Iterate the rosbag
    bag_len = cam.getBagLength(topics)
    img_count = 0
    while True:
        cprint.info(f'\tImage {img_count}/{bag_len}')
        img_count += 1
        try:
            image, _ = cam.getImages()
        except StopIteration:
            cprint.ok('ROSBag completed!')
            break

        image = np.array(Image.fromarray(image).resize(input_shape[:2]))
        if arch == 'ssd':
            feed_dict = {net.image_tensor: image[None, ...]}
            out, elapsed = net._forward_pass(feed_dict)
            n_dets = int(out[-1][0])
        else:
            cprint.fatal(f'{arch} benchmarking not implemented yet!', interrupt=True)

        total_times.append([elapsed, n_dets])

    # The benchmark is finished. We log the results now.
    net.sess.close()
    writer = SingleModelBenchmarker(save_in)
    writer.write_benchmark(total_times, pb_file, rosbag_file, arch, write_iters=True)