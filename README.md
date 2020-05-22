# ProMP-Implementation
## Project Description
This project implements an Interaction Probabilistic Movement Primitive as introduced by Maeda, et al. in the following paper:
Maeda, Guilherme, et al. "Phase estimation for fast action recognition and trajectory generation in human–robot collaboration." The International Journal of Robotics Research 36.13-14 (2017): 1579-1594.

The goal of the algorithm is to train a robot on a specific task through multiple demonstrations and have it generalize the training demonstrations in order to collaborate with a human seamlessly, i.e. with perfect spatial and temporal coordination.

In the test case used to validate this implementation, the robot writes the letter B when the human writes the letter A. From the following
image, the good spatial performance of the algorithm is clear.



For the temporal coordination, the algorithm used was different from the one given in the paper. The scaling factor for the observation
trajectory was estimated by comparing the trajectory with similar training trajectories. The error in estimated trajectory duration and actual trajectory duration was limited to 6%.

## Acknowledgements
I would like to thank @hsnemlekar for his help during the project and his code which served as an initial jumping off point for this project. 
I would also like to thank Guilherme Maeda and Marco Ewerton for their help.
