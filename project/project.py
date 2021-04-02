#!/usr/bin/python
# -*- coding: utf-8 -*-

import cv2
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import pyforms
from numpy import dot
from pyforms import BaseWidget
from pyforms.controls import ControlButton, ControlText, ControlSlider, \
    ControlFile, ControlPlayer, ControlCheckBox, ControlCombo, ControlProgress
from scipy.spatial.distance import squareform, pdist

from helpers.functions import get_log_kernel, inv, linear_sum_assignment, \
    local_maxima, select_frames, local_maxima_blobs, blob_detect
from helpers.video_window import VideoWindow


class MultipleBlobDetection(BaseWidget):
    def __init__(self):
        super(MultipleBlobDetection, self).__init__(
            'Multiple Blob Detection')

        # Definition of the forms fields
        self._videofile = ControlFile('Video')
        self._outputfile = ControlText('Results output file')

        self._threshold_box = ControlCheckBox('Threshold')
        self._threshold = ControlSlider('Binary Threshold')
        self._threshold.value = 114
        self._threshold.min = 1
        self._threshold.max = 255
        self._roi_x_min = ControlSlider('ROI x top')
        self._roi_x_max = ControlSlider('ROI x bottom')
        self._roi_y_min = ControlSlider('ROI y left')
        self._roi_y_max = ControlSlider('ROI y right')
        # self._blobsize = ControlSlider('Minimum blob size', 100, 100, 2000)
        self._player = ControlPlayer('Player')
        self._runbutton = ControlButton('Run')
        self._start_frame = ControlText('Start Frame')
        self._stop_frame = ControlText('Stop Frame')

        self._color_list = ControlCombo('Color channels')
        self._color_list.add_item('Red Image Channel', 2)
        self._color_list.add_item('Green Image Channel', 1)
        self._color_list.add_item('Blue Image Channel', 0)

        self._clahe = ControlCheckBox('CLAHE      ')
        self._dilate = ControlCheckBox('Morphological Dilation')
        self._dilate_type = ControlCombo('Dilation Kernel Type')
        self._dilate_type.add_item('RECTANGLE', cv2.MORPH_RECT)
        self._dilate_type.add_item('ELLIPSE', cv2.MORPH_ELLIPSE)
        self._dilate_type.add_item('CROSS', cv2.MORPH_CROSS)
        self._dilate_size = ControlSlider('Dilation Kernel Size', default=3,
                                          min=1, max=10)
        self._dilate_size.value = 5
        self._dilate_size.min = 1
        self._dilate_size.max = 10

        self._erode = ControlCheckBox('Morphological Erosion')
        self._erode_type = ControlCombo('Erode Kernel Type')
        self._erode_type.add_item('RECTANGLE', cv2.MORPH_RECT)
        self._erode_type.add_item('ELLIPSE', cv2.MORPH_ELLIPSE)
        self._erode_type.add_item('CROSS', cv2.MORPH_CROSS)

        self._erode_size = ControlSlider('Erode Kernel Size')
        self._erode_size.value = 5
        self._erode_size.min = 1
        self._erode_size.max = 10

        self._open = ControlCheckBox('Morphological Opening')
        self._open_type = ControlCombo('Open Kernel Type')
        self._open_type.add_item('RECTANGLE', cv2.MORPH_RECT)
        self._open_type.add_item('ELLIPSE', cv2.MORPH_ELLIPSE)
        self._open_type.add_item('CROSS', cv2.MORPH_CROSS)

        self._open_size = ControlSlider('Open Kernel Size')
        self._open_size.value = 20
        self._open_size.min = 1
        self._open_size.max = 40

        self._close = ControlCheckBox('Morphological Closing')
        self._close_type = ControlCombo('Close Kernel Type')
        self._close_type.add_item('RECTANGLE', cv2.MORPH_RECT)
        self._close_type.add_item('ELLIPSE', cv2.MORPH_ELLIPSE)
        self._close_type.add_item('CROSS', cv2.MORPH_CROSS)
        self._close_size = ControlSlider('Close Kernel Size', default=19,
                                         min=1, max=40)
        self._close_size.value = 20
        self._close_size.min = 1
        self._close_size.max = 40

        self._LoG = ControlCheckBox('LoG - Laplacian of Gaussian')
        self._LoG_size = ControlSlider('LoG Kernel Size')
        self._LoG_size.value = 20
        self._LoG_size.min = 1
        self._LoG_size.max = 60

        self._progress_bar = ControlProgress('Progress Bar')

        # Define the function that will be called when a file is selected
        self._videofile.changed_event = self.__video_file_selection_event
        # Define the event that will be called when the run button is processed
        self._runbutton.value = self.__run_event
        # Define the event called before showing the image in the player
        self._player.process_frame_event = self.__process_frame
        
        self._error_massages = {}

        # Define the organization of the Form Controls
        self.formset = [
            ('_videofile', '_outputfile'),
            ('_start_frame', '_stop_frame'),
            ('_color_list', '_clahe', '_roi_x_min', '_roi_y_min'),
            ('_threshold_box', '_threshold', '_roi_x_max', '_roi_y_max'),
            ('_dilate', '_erode', '_open', '_close'),
            ('_dilate_type', '_erode_type', '_open_type', '_close_type'),
            ('_dilate_size', '_erode_size', '_open_size', '_close_size'),
            ('_LoG', '_LoG_size'),
            ('_runbutton', '_progress_bar'),
            '_player'
        ]
        self.is_roi_set = False
        
        self.max_num_objects = 75000
        self.blob_detector = blob_detect()


    def _parameters_check(self):
        self._error_massages = {}
        if not self._player.value:
            self._error_massages['video'] = 'No video specified'
        elif not self._start_frame.value or not self._stop_frame.value or \
                int(self._start_frame.value) >= int(self._stop_frame.value) or \
                int(self._start_frame.value) < 0 or int(self._stop_frame.value) < 0:
            self._error_massages['frames'] = 'Wrong start/end frame number'

    def __video_file_selection_event(self):
        """
        When the video file is selected instanciate the video in the player
        """
        self._player.value = self._videofile.value

    def __color_channel(self, frame):
        """
        Returns only one color channel of input frame.
        Output is in grayscale.
        """
        frame = frame[:, :, self._color_list.value]
        return frame

    def __create_kernels(self):
        """
        Creates kernels for morphological operations.
        Check cv2.getStructuringElement() doc for more info:
        http://docs.opencv.org/3.0-beta/doc/py_tutorials/py_imgproc/
        py_morphological_ops/py_morphological_ops.html

        Assumed that all kernels (except LoG kernel) are square.
        Example of use:
        open_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
        erosion_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        :return: _opening_kernel, _close_kernel, _erosion_kernel, \
            _dilate_kernel, _LoG_kernel
        """
        if self._open_type.value and self._open_size.value:
            _opening_kernel = cv2.getStructuringElement(self._open_type.value,
                                                        (self._open_size.value,
                                                         self._open_size.value))
        else:
            _opening_kernel = None

        if self._close_type.value and self._close_size.value:
            _close_kernel = cv2.getStructuringElement(self._close_type.value,
                                                      (self._close_size.value,
                                                       self._close_size.value))
        else:
            _close_kernel = None

        if self._erode_type.value and self._erode_size.value:
            _erosion_kernel = cv2.getStructuringElement(self._erode_type.value,
                                                        (self._erode_size.value,
                                                         self._erode_size.value))
        else:
            _erosion_kernel = None

        if self._dilate_type.value and self._dilate_size.value:
            _dilate_kernel = cv2.getStructuringElement(self._dilate_type.value,
                                                       (self._dilate_size.value,
                                                        self._dilate_size.value))
        else:
            _dilate_kernel = None

        if self._LoG.value and self._LoG_size.value:
            _LoG_kernel = get_log_kernel(self._LoG_size.value,
                                         int(self._LoG_size.value * 0.5))
        else:
            _LoG_kernel = None

        return _opening_kernel, _close_kernel, _erosion_kernel, \
            _dilate_kernel, _LoG_kernel

    def __morphological(self, frame):
        """
        Apply morphological operations selected by the user.
        :param frame: input frame of selected video.
        :return: preprocessed frame.
        """
        opening_kernel, close_kernel, erosion_kernel, \
        dilate_kernel, log_kernel = self.__create_kernels()
        # prepare image - morphological operations
        if self._erode.value:
            frame = cv2.erode(frame, erosion_kernel, iterations=1)
        if self._open.value:
            frame = cv2.morphologyEx(frame, cv2.MORPH_OPEN, opening_kernel)
        if self._close.value:
            frame = cv2.morphologyEx(frame, cv2.MORPH_CLOSE, close_kernel)
        if self._dilate.value:
            frame = cv2.dilate(frame, dilate_kernel, iterations=1)
            # create LoG kernel for finding local maximas
        if self._LoG.value:
            frame = cv2.filter2D(frame, cv2.CV_32F, log_kernel)
            frame *= 255
            # remove near 0 floats
            frame[frame < 1e-5] = 0
            frame = frame.astype('uint8')
        return frame

    def __roi(self, frame):
        """
        Define image region of interest.
        """
        # ROI
        height, width = frame.shape
        self._roi_x_max.min = int(height / 2)
        self._roi_x_max.max = height
        self._roi_y_max.min = int(width / 2)
        self._roi_y_max.max = width

        self._roi_x_min.min = 0
        self._roi_x_min.max = int(height / 2)
        self._roi_y_min.min = 0
        self._roi_y_min.max = int(width / 2)

        if not self.is_roi_set:
            self._roi_x_max.value = height
            self._roi_y_max.value = width
            self.is_roi_set = True

        # x axis
        frame[:int(self._roi_x_min.value)][::] = 255
        frame[int(self._roi_x_max.value)::][::] = 255
        # y axis
        for m in range(height):  # height
            for n in range(width):  # width
                if n > self._roi_y_max.value or n < self._roi_y_min.value:
                    frame[m][n] = 255

        # frame[0::][:int(self._roi_y_min.value)] = 255
        # frame[0::][int(self._roi_y_max.value):] = 255
        return frame

    def _kalman(self, max_points, stop_frame, vid_fragment):
        """
        Kalman Filter function. Takes measurements from video analyse function
        and estimates positions of detected objects. Munkres algorithm is used
        for assignments between estimates (states) and measurements.
        :param max_points: measurements.
        :param stop_frame: number of frames to analise
        :param vid_fragment: video fragment for estimates displaying
        :return: x_est, y_est - estimates of x and y positions in the following
                 format: x_est[index_of_object][frame] gives x position of object
                 with index = [index_of_object] in the frame = [frame]. The same
                 goes with y positions.
        """
        # font for displaying info on the image
        index_error = 0
        value_error = 0
        # step of filter
        dt = 1.
        R_var = 1  # measurements variance between x-x and y-y
        # Q_var = 0.1  # model variance
        # state covariance matrix - no initial covariances, variances only
        # [10^2 px, 10^2 px, ..] -
        P = np.diag([100, 100, 10, 10, 1, 1])
        # state transition matrix for 6 state variables
        # (position - velocity - acceleration,
        # x, y)
        F = np.array([[1, 0, dt, 0, 0.5 * pow(dt, 2), 0],
                      [0, 1, 0, dt, 0, 0.5 * pow(dt, 2)],
                      [0, 0, 1, 0, dt, 0],
                      [0, 0, 0, 1, 0, dt],
                      [0, 0, 0, 0, 1, 0],
                      [0, 0, 0, 0, 0, 1]])
        # x and y coordinates only - measurements matrix
        H = np.array([[1., 0., 0., 0., 0., 0.],
                      [0., 1., 0., 0., 0., 0.]])
        # no initial corelation between x and y positions - variances only
        R = np.array(
            [[R_var, 0.], [0., R_var]])  # measurement covariance matrix
        # Q must be the same shape as P
        Q = np.diag([100, 100, 10, 10, 1, 1])  # model covariance matrix

        # create state vectors, max number of states - as much as frames
        x = np.zeros((self.max_num_objects, 6))
        # state initialization - initial state is equal to measurements
        m = 0
        try:
            for i in range(len(max_points[0])):
                if max_points[0][i][0] > 0 and max_points[0][i][1] > 0:
                    x[m] = [max_points[0][i][0], max_points[0][i][1],
                            0, 0, 0, 0]
                    m += 1
        except IndexError:
            index_error = 1

        est_number = 0
        # number of estimates at the start
        try:
            for point in max_points[::][0]:
                if point[0] > 0 and point[1] > 0:
                    est_number += 1
        except IndexError:
            index_error = 1

        # history of new objects appearance
        new_obj_hist = [[]]
        # difference between position of n-th object in m-1 frame and position
        # of the same object in m frame
        diff_2 = [[]]
        # for how many frames given object was detected
        frames_detected = []
        # x and y posterior positions (estimates) for drawnings
        x_est = [[] for i in range(stop_frame)]
        y_est = [[] for i in range(stop_frame)]

        # variable for counting frames where object has no measurement
        striked_tracks = np.zeros(stop_frame)
        removed_states = []
        new_detection = []
        ff_nr = 0  # frame number

        self._progress_bar.label = '3/4: Generating position estimates..'
        self._progress_bar.value = 0
        print('3/4: Generating position estimates...')

        # kalman filter loop
        for frame in range(stop_frame):
            self._progress_bar.value = 100 * (ff_nr / stop_frame)
            # measurements in one frame
            try:
                frame_measurements = max_points[::][frame]
            except IndexError:
                index_error = 1

            measurements = []
            # make list of lists, not tuples; don't take zeros,
            # assuming it's image
            if not index_error:
                for meas in frame_measurements:
                    if meas[0] > 0 and meas[1] > 0:
                        measurements.append([meas[0], meas[1]])
            # count prior
            for i in range(est_number):
                x[i][::] = dot(F, x[i][::])
            P = dot(F, P).dot(F.T) + Q
            S = dot(H, P).dot(H.T) + R
            K = dot(P, H.T).dot(inv(S))
            ##################################################################
            # prepare for update phase -> get (prior - measurement) assignment
            posterior_list = []
            for i in range(est_number):
                if not np.isnan(x[i][0]) and not np.isnan(x[i][1]):
                    posterior_list.append(i)
                    # print(i)
            # print(posterior_list)
            #
            # print('state\n', x[0:est_number, 0:2])
            # print('\n')
            #    temp_matrix = np.array(x[0:est_number, 0:2])
            try:
                temp_matrix = np.array(x[posterior_list, 0:2])
                temp_matrix = np.append(temp_matrix, measurements, axis=0)
            except ValueError:
                value_error = 1

            # print(temp_matrix)
            distance = pdist(temp_matrix, 'euclidean')  # returns vector

            # make square matrix out of vector
            distance = squareform(distance)
            temp_distance = distance
            # remove elements that are repeated - (0-1), (1-0) etc.
            #    distance = distance[est_number::, 0:est_number]
            distance = distance[0:len(posterior_list), len(posterior_list)::]

            # munkres
            row_index, column_index = linear_sum_assignment(distance)
            final_cost = distance[row_index, column_index].sum()
            unit_cost = []
            index = []
            for i in range(len(row_index)):
                # index(object, measurement)
                index.append([row_index[i], column_index[i]])
                unit_cost.append(distance[row_index[i], column_index[i]])

            ##################################################################
            # index correction - take past states into account
            removed_states.sort()
            for removed_index in removed_states:
                for i in range(len(index)):
                    if index[i][0] >= removed_index:
                        index[i][0] += 1
            ##################################################################
            # find object to reject
            state_list = [index[i][0] for i in range(len(index))]
            reject = np.ones(len(posterior_list))
            i = 0
            for post_index in posterior_list:
                if post_index not in state_list:
                    reject[i] = 0
                i += 1
            # check if distance (residual) isn't to high for assignment
            for i in range(len(unit_cost)):
                if unit_cost[i] > 20:
                    # print('cost to high, removing', i)
                    reject[i] = 0

            ##################################################################
            # update phase
            for i in range(len(index)):
                # find object that should get measurement next
                # count residual y: measurement - state
                if index[i][1] >= 0:
                    y = np.array([measurements[index[i][1]] -
                                  dot(H, x[index[i][0], ::])])
                    # posterior
                    x[index[i][0], ::] = x[index[i][0], ::] + dot(K, y.T).T
                    # append new positions
                #        if x[i][0] and x[i][1]:

                x_est[index[i][0]].append({'frame': frame,
                                           'x_position': [x[index[i][0], 0]][0],
                                           'index': index[i][0]})
                y_est[index[i][0]].append({'frame': frame,
                                           'y_position': [x[index[i][0], 1]][0],
                                           'index': index[i][0]})

            # posterior state covariance matrix
            P = dot(np.identity(6) - dot(K, H), P)
            print('posterior\n', x[0:est_number, 0:2])
            ##################################################################
            # find new objects and create new states for them
            new_index = []
            measurement_indexes = []
            for i in range(len(index)):
                if index[i][1] >= 0.:
                    # measurements that have assignment
                    measurement_indexes.append(index[i][1])

            for i in range(len(measurements)):
                if i not in measurement_indexes:
                    # find measurements that don't have assignments
                    new_index.append(i)
            new_detection.append([measurements[new_index[i]]
                                  for i in range(len(new_index))])
            x_max = x.shape[0]
            # for every detections in the last frame
            for i in range(len(new_detection[frame])):
                # add new estimate only if it's near nozzles
                # TODO: make it possible to choose where to add new estimates
                #if new_detection[frame][i] and \
                #                new_detection[frame][i][0] > 380:
                
                try:
                    x[est_number, ::] = [new_detection[frame][i][0],
                                         new_detection[frame][i][1], 0, 0, 0, 0]
                    est_number += 1
                    if est_number == x_max:
                        break
                except IndexError:
                    import pdb; pdb.set_trace()
                    print('h')
                    # print('state added', est_number)
                    # print('new posterior\n', x[0:est_number, 0:2])
            ##################################################################
            # find states without measurements and remove them
            no_track_list = []
            for i in range(len(reject)):
                if not reject[i]:
                    no_track_list.append(posterior_list[i])
                    #    print('no_trk_list', no_track_list)
            for track in no_track_list:
                if track >= 0:
                    striked_tracks[track] += 1
                    print('track/strikes', track, striked_tracks[track])
            for i in range(len(striked_tracks)):
                # remove estimate if it's strike max_strike_count times
                # (has no assigned detection for max_strike_count consecutive frames)
                max_strike_count = 4
                if striked_tracks[i] >= max_strike_count:
                    x[i, ::] = [None, None, None, None, None, None]
                    if i not in removed_states:
                        removed_states.append(i)
                    print('state_removed', i)
            ff_nr += 1
                # print(removed_states)
                # print(index)
            print('FRAME NUBMER: ', ff_nr)
        return x_est, y_est, est_number

    def _plot_points(self, vid_frag, max_points, x_est, y_est, est_number):
        self._progress_bar.label = '4/4: Plotting - measurements..'
        self._progress_bar.value = 0
        # plot raw measurements
        for frame_positions in max_points:
            for pos in frame_positions:
                # raw measurements as red dots
                plt.plot(pos[0], pos[1], 'r.')
        # try:
        # axis size the same as frame size
        plt.axis([0, vid_frag[0].shape[1], vid_frag[0].shape[0], 0])
        # except IndexError:
        #     index_error = 1
        plt.xlabel('width [px]')
        plt.ylabel('height [px]')
        plt.title('Objects raw measurements')
        ######################################################################
        # image border - 10 px
        x_max = vid_frag[0].shape[1] - 10
        y_max = vid_frag[0].shape[0] - 10

        self._progress_bar.label = '4/4: Plotting - estimates..'
        self._progress_bar.value = 0
        i = 0
        # plot estimated trajectories
        for ind in range(est_number):
            self._progress_bar.value = 100 * (i / est_number)
            i += 1
            # if estimate exists
            if len(x_est[ind]):
                for pos in range(len(x_est[ind])):
                    # don't draw near 0 points and near max points
                    if not np.isnan(x_est[ind][pos]['x_position']) and \
                                    x_est[ind][pos]['x_position'] > 10 and \
                                    y_est[ind][pos]['y_position'] > 10 and \
                                    x_est[ind][pos]['x_position'] < x_max - 10 and \
                                    y_est[ind][pos]['y_position'] < y_max - 10:
                        # plot estimates as green dots
                        plt.plot(x_est[ind][pos]['x_position'], y_est[ind][pos]['y_position'], 'g.')
                        # plt.plot(x_est[ind][::], y_est[ind][::], 'g-')
        # print(frame)
        #  [xmin xmax ymin ymax]
        # try:
        plt.axis([0, vid_frag[0].shape[1], vid_frag[0].shape[0], 0])
        # except IndexError:
        #     index_error = 1
        plt.xlabel('width [px]')
        plt.ylabel('height [px]')
        plt.title('Objects estimated trajectories')
        plt.grid()
        plt.show()

    def __process_frame(self, frame):
        """
        Do some processing to the frame and return the result frame
        """
        # frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        frame = self.__color_channel(frame)

        if self._clahe.value:
            clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8, 8))
            frame = clahe.apply(frame)

        frame = self.__roi(frame)

        if self._threshold_box.value:
            ret, frame = cv2.threshold(frame, self._threshold.value, 255,
                                       cv2.THRESH_BINARY)
            frame = self.__morphological(frame)
        return frame

    def __run_event(self):
        """
        After setting the best parameters run the full algorithm
        """
        height = 0
        width = 0
        self._parameters_check()
        if not len(self._error_massages):
            start_frame = int(self._start_frame.value)
            stop_frame = int(self._stop_frame.value)
            # pass cv2.VideoCapture object, not string
            # my_video = self._player.value
            video = self._player.value
            # self._load_bar.__init__('Processing..')
            vid_fragment = select_frames(video, start_frame, stop_frame)
            try:
                height = vid_fragment[0].shape[0]
                width = vid_fragment[0].shape[1]
            except IndexError:
                self._error_massages['video'] = 'No video specified'

            i = 0
            bin_frames = []
            # preprocess image loop
            self._progress_bar.label = '1/4: Creating BW frames..'
            print('1/4: Creating BW frames...')
            self._progress_bar.value = 0
            for frame in vid_fragment:
                gray_frame = self.__color_channel(frame)
                # create a CLAHE object (Arguments are optional)
                if self._clahe.value:
                    clahe = cv2.createCLAHE(clipLimit=8.0, tileGridSize=(8, 8))
                    gray_frame = clahe.apply(gray_frame)

                # ROI
                gray_frame = self.__roi(gray_frame)
                ret, th1 = cv2.threshold(gray_frame, self._threshold.value, 255,
                                         cv2.THRESH_BINARY)
                # frame_thresh1 = otsu_binary(cl1)
                bin_frames.append(th1)
                self._progress_bar.value = 100 * (i / len(vid_fragment))
                i += 1

            i = 0
            maxima_points = []
            # gather measurements loop
            
            self._progress_bar.label = '2/4: Finding local maximas..'
            self._progress_bar.value = 0
            print('2/4: Finding local maxima...')
            for frame in bin_frames:
                frame = self.__morphological(frame)
                # get local maximas of filtered image per frame
                maxima_points.append(local_maxima_blobs(frame, self.blob_detector))
                self._progress_bar.value = 100 * (i / len(bin_frames))
                i += 1

            # try:
            x_est, y_est, est_number = self._kalman(maxima_points,
                                                    stop_frame,
                                                    vid_fragment)
            print('\nFinal estimates number:', est_number)
            fourcc = cv2.VideoWriter_fourcc(*'MJPG')
            out_vid = cv2.VideoWriter('blob.avi', fourcc, 20, (1280, 720))
            
            #cv2.namedWindow(winname='frame', flags=cv2.WINDOW_KEEPRATIO)
            cap = cv2.VideoCapture(self._videofile.value)
            outfile = open(self._outputfile.value, 'w')
            outfile.write('frame,ID,x,y\n')

            frame_number = 0
            while cap.isOpened():
                ret, frame = cap.read()
                # mark detections on the frame - blue dots
                for pos_index in range(len(maxima_points[frame_number])):
                    tmp_x = int(maxima_points[frame_number][pos_index][0])
                    tmp_y = int(maxima_points[frame_number][pos_index][1])
                    cv2.circle(frame, (tmp_x, tmp_y), 2, (255, 0, 0), -1)

                # for estimates
                for est in range(len(x_est)):
                    if x_est[est] and y_est[est]:
                        try:
                            tmp_x = int(list(filter(lambda x: x['frame'] == frame_number, x_est[est]))[0]['x_position'])
                            tmp_y = int(list(filter(lambda y: y['frame'] == frame_number, y_est[est]))[0]['y_position'])
                            float_x = list(filter(lambda x: x['frame'] == frame_number, x_est[est]))[0]['x_position']
                            float_y = list(filter(lambda y: y['frame'] == frame_number, y_est[est]))[0]['y_position']
                            # mark estimates on the frame - red dots
                            cv2.circle(frame, (tmp_x, tmp_y), 2, (0, 0, 255), -1)
                            cv2.putText(frame, str(est),
                                        (tmp_x + 5, tmp_y - 5),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                        (0, 0, 255), 1, cv2.LINE_AA)
                            outfile.write('{},{},{},{}\n'.format(frame_number, est, float_x, float_y))
                        except IndexError:
                            pass
                # draw frame counter
                if height:
                    cv2.putText(frame, 'f_nr: ' + str(frame_number),
                                (50, height - 10),
                                cv2.FONT_HERSHEY_COMPLEX, 0.3, (255, 255, 255),
                                1, cv2.LINE_AA)

                #cv2.imshow(winname='frame', mat=frame)
                out_vid.write(frame)
                frame_number += 1
                #if cv2.waitKey(100) & 0xFF == ord('q') or \
                #        frame_number >= int(self._stop_frame.value):
                #    break
                if cv2.waitKey(100) & 0xFF == ord('q') or \
                        frame_number == len(maxima_points):
                    break

            cap.release()
            out_vid.release()
            cv2.destroyAllWindows()
            #self._plot_points(vid_fragment, maxima_points, x_est,
            #                  y_est, est_number)
            # except IndexError:
            #     self._progress_bar.label += ' ' + 'ERROR while generating estimates. ' \
            #                                       'Try adjusting parameters.'
            outfile.close()
        else:
            self._progress_bar.label = 'WRONG PARAMETERS:'
            for key in self._error_massages:
                self._progress_bar.label += ' ' + self._error_massages[key]


# Execute the application
if __name__ == "__main__":
    pyforms.start_app(MultipleBlobDetection)

print('EOF')
