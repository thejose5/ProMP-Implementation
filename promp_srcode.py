import sys, time, os
import numpy as np
import statistics
import scipy.stats
import matplotlib.pyplot as plt
import math
from scipy import linalg


class ProMP:
    def __init__(self, ndemos=50, hum_dofs=2, robot_dofs=2, dt=0.1, training_address="Data\Human A Robot B 1"):
        self.ndemos = ndemos
        self.human_dofs = hum_dofs
        self.robot_dofs = robot_dofs
        self.nBasis = 30 # No. of basis functions per time step...
        self.noise_stdev = 1
        self.dt = dt

        # data is a list, the ith element of which represents an Nx4 array containing the data of the ith demo
        self.data = self.loadData(training_address,dt)
        print("Data Loaded")
        # Time normalization and encoding alpha
        self.alpha, self.alphaM, self.alphaV, self.mean_time_steps = self.PhaseNormalization(self.data)
        # print("Alphas Obtained")
        # Normalize the data by writing it in terms of phase variable z. dz = alpha*dt
        self.ndata = self.normalizeData(self.alpha, self.dt, self.data, (self.robot_dofs+self.human_dofs),self.mean_time_steps)
        print("Data Normalized")
        # Now generate a gaussian basis and find the weights using this basis
        self.promp = self.pmpRegression(self.ndata)
        # self.param = {"nTraj": self.p_data["size"], "nTotalJoints": self.promp["nJoints"],
        #               "observedJointPos": np.array(range(obs_dofs)), "observedJointVel": np.array([])}
        self.alpha_samples = np.linspace(min(self.alpha),max(self.alpha),100)

        # The following 3 variables are used in querying phase only
        self.mu_new = self.promp["w"]["mean_full"]
        self.cov_new = self.promp["w"]["cov_full"]
        self.obsdata = np.empty((0,(self.promp["nJoints"])))
        # self.obsndata = np.empty((0, (self.promp["nJoints"])))
        print("Initialization Complete")

    def loadData(self, addr, dt):
        data = []
        for i in range(self.ndemos):
            human = np.loadtxt(open(addr + "\letterAtr" + str(i + 1) + ".csv"), delimiter=",")
            robot = np.loadtxt(open(addr + "\letterBtr" + str(i + 1) + ".csv"), delimiter=",")
            temp = np.concatenate((human,robot),axis=1)
            data.append(temp)

        return data

    def PhaseNormalization(self, data):

        sum = 0
        for i in range(len(data)):
            sum += len(data[i])
        mean = sum / len(data)
        alpha = []
        for i in range(len(data)):
            alpha.append(len(data[i]) / mean)

        alpha_mean = statistics.mean(alpha)
        alpha_var = statistics.variance(alpha)

        return alpha, alpha_mean, alpha_var, int(mean)

    def normalizeData(self, alpha, dt, data, dofs, mean_t):

        # normalize the data to contain same number of data points
        ndata = []
        for i in range(len(alpha)):
            demo_ndata = np.empty((0, dofs))
            for j in range(mean_t):  # Number of phase steps is same as number of time steps in nominal trajectory, because for nominal traj alpha is 1
                z = j * alpha[i] * dt
                corr_timestep = z / dt
                whole = int(corr_timestep)
                if whole == (data[i].shape[0] - 1):
                    frac = 0
                else:
                    frac = corr_timestep - whole
                row = []
                for k in range(dofs):
                    row.append(data[i][whole][k] + frac * (data[i][whole + 1][k] - data[i][whole][k]))
                demo_ndata = np.append(demo_ndata, [row], axis=0)
            # phasestamp = np.linspace(0,alpha[i]*dt*(demo_ndata.shape[0]-1),demo_ndata.shape[0])
            # phasestamp = phasestamp.reshape((phasestamp.shape[0],1))
            # demo_ndata = np.concatenate((demo_ndata,phasestamp),axis=1)
            ndata.append(demo_ndata)

        return ndata

    def pmpRegression(self, data):
        nJoints = data[0].shape[1]
        nDemo = len(data)
        nTraj = data[0].shape[0]
        nBasis = self.nBasis

        weight = {"nBasis": nBasis, "nJoints": nJoints, "nDemo": nDemo, "nTraj":nTraj}
        weight["my_linRegRidgeFactor"] = 1e-08 * np.identity(nBasis)

        basis = self.generateGaussianBasis(self.dt, nTraj,nBasis)
        weight = self.leastSquareOnWeights(weight, basis, data)

        pmp = {"w": weight, "basis": basis, "nBasis": nBasis, "nJoints": nJoints, "nDemo": nDemo, "nTraj":nTraj}

        return pmp

    def generateGaussianBasis(self, dt, nTraj, nBasis):
        basisCenter = np.linspace(0, nTraj * dt, nBasis) # Assuming the average for our basis functions
        sigma = 0.5 * np.ones((1, nBasis))
        z = np.linspace(0, dt * (nTraj-1), nTraj)
        z_minus_center = np.matrix(z).T - np.matrix(basisCenter)
        at = np.multiply(z_minus_center, (1.0 / sigma)) # (z-mu)/sigma for each z, each sigma and each mu.     np.multiply = elementwise multiplication

        basis = np.multiply(np.exp(-0.5 * np.power(at, 2)), 1. / sigma / np.sqrt(2 * np.pi)) #root(2pi)/sigma*e^(-((z-mu)/sigma)^2/2)
        basis_sum = np.sum(basis, axis=1)
        basis_n = np.multiply(basis, 1.0 / basis_sum) # Normalized basis? (Tnom)x(nBasis)

        return basis_n

    def leastSquareOnWeights(self, weight, Gn, data):
        weight["demo_q"] = data
        nDemo = weight["nDemo"]
        nJoints = weight["nJoints"]
        nBasis = weight["nBasis"]
        my_linRegRidgeFactor = weight["my_linRegRidgeFactor"]

        MPPI = np.linalg.solve(Gn.T * Gn + my_linRegRidgeFactor, Gn.T)

        w, ind = [], []
        for i in range(nJoints):
            w_j = np.empty((0, nBasis), float)
            for j in range(nDemo):
                w_ = MPPI * np.matrix(data[j][:, i]).T # weights for the jth demo's ith dof (30x1)
                w_j = np.append(w_j, w_.T, axis=0)
            w.append(w_j)
            ind.append(np.matrix(range(i * nBasis, (i + 1) * nBasis)))

        weight["index"] = ind
        weight["w_full"] = np.empty((nDemo, 0), float)
        for i in range(nJoints):
            weight["w_full"] = np.append(weight["w_full"], w[i], axis=1) # nDemos x (nBasis*nJoints)

        weight["cov_full"] = np.cov(weight["w_full"].T)  # (num of bases*num of dofs) x (num of bases*num of dofs)
        weight["mean_full"] = np.mean(weight["w_full"], axis=0).T  # (num of bases*num of dofs) x 1

        return weight

    def predict(self, data,alpha_real=1):
        promp = self.promp
        mu_new = self.mu_new
        cov_new = self.cov_new
        self.obsdata = np.append(self.obsdata,data,axis=0) # accumulate all the data from previous steps
        alpha = self.findAlpha(self.obsdata)
        true_alpha = alpha_real
        obsndata = self.normalizeObservation(self.obsdata, alpha)

        mu_new, cov_new = self.conditionNormDist(obsndata, alpha, mu_new, cov_new)
        prdct_data_z = self.weightsToTrajs(promp, mu_new)
        prdct_data_t = self.z2t(prdct_data_z, alpha)
        return prdct_data_t

    def findAlpha(self, obs):
        data = self.data
        alphas = self.alpha
        obsdofs = self.human_dofs
        bestalpha = 1
        startfrom = 2
        for j in range(startfrom,obs.shape[0]):
            min = np.inf
            for i in range(len(data)):
                if(data[i].shape[0]-1>=j):
                    diff = data[i][j,:] - obs[j,:]
                    sumsqr=0
                    for k in range(obsdofs):
                        sumsqr = sumsqr+diff[k]**2
                    meansqr = sumsqr/(k+1)
                    rms = np.sqrt(meansqr)
                    if(rms<min):
                        min = rms
                        minind = i
            bestalpha = (alphas[minind]+bestalpha*(j-startfrom))/(j+1-startfrom)
        return bestalpha

        # Find log probability of observation given alpha and log probability of alpha and add the two
        # This gives log probability of alpha given observation. The alpha with max of this prob is the winner
        # alpha_samples = self.alpha_samples
        # alphaM = self.alphaM
        # alphaV = self.alphaV
        # alpha_dist = scipy.stats.norm(alphaM,alphaV)
        # lprob_alphas = []
        # inv_obs_noise = 0.00001
        # mu_w = self.promp["w"]["mean_full"]
        # sig_w = self.promp["w"]["cov_full"]
        # dt = self.dt
        #
        # for i in range(alpha_samples.shape[0]):
        #     # log probability (actually likelihood) alpha
        #     lp_alpha = math.log(alpha_dist.pdf(alpha_samples[i]))
        #
        #     # log probability (actually likelihood) of observation given alpha
        #     nTraj = int(obs.shape[0]/alpha_samples[i])
        #     nBasis = self.nBasis
        #     basis = self.generateGaussianBasis(alpha_samples[i]*dt,nTraj,nBasis)
        #     lp_obs_alpha = self.computeLogProbObs_alpha(obs,basis,mu_w,sig_w,alpha_samples[i],inv_obs_noise)
        #     lprob_alphas.append(lp_alpha+lp_obs_alpha)
        #
        # best_alpha_index = lprob_alphas.index(max(lprob_alphas))
        # best_alpha = alpha_samples[best_alpha_index]

        # return best_alpha



    def computeLogProbObs_alpha(self, obs,basis,mu_w,sig_w,alpha_sample,inv_obs_noise):

        length_obs_t = obs.shape[0]
        length_obs_z = int(length_obs_t/alpha_sample)
        if(length_obs_z <= self.mean_time_steps):
            obs_dofs = self.human_dofs
            obs = self.normalizeObservation(obs,alpha_sample)
            obs = obs[:, 0:obs_dofs]
            nTraj = basis.shape[0]
            nBasis = basis.shape[1]
            mu_w = mu_w[np.linspace(0,obs_dofs*nBasis-1,obs_dofs*nBasis,dtype=int),:]
            sig_w = sig_w[0:obs_dofs*nBasis,0:obs_dofs*nBasis]

            # Define A matrix:
            A = np.zeros((obs_dofs*nTraj,obs_dofs*nBasis))
            for i in range(obs_dofs):
                A[i*nTraj:(i+1)*nTraj,i*nBasis:(i+1)*nBasis] = basis
            # end Define A matrix:
            a = inv_obs_noise
            u = A*mu_w
            # Writing observation data in a single column
            obs_new = np.zeros((obs.shape[0] * obs.shape[1], 1))
            for i in range(obs.shape[1]):
                obs_new[i*obs.shape[0]:(i+1)*obs.shape[0],:] = np.reshape(obs[:,i],(obs[:,i].shape[0],1))
            sigma = (1/a)*np.identity(A.shape[0]) + np.matmul(A,np.matmul(sig_w,A.T))
            sigma_chol = np.linalg.cholesky(2*np.pi*sigma).T # Transposed because in MATLAB, chol() returns upper triang matrix
            diag_sig = np.diag(sigma_chol)
            sum_log_diag = 0
            for i in range(diag_sig.shape[0]):
                sum_log_diag = sum_log_diag + math.log(diag_sig[i])
            log_p = -sum_log_diag - (1/2)*np.matmul((obs_new.T-u.T),np.matmul(np.linalg.inv(sigma),(obs_new.T - u.T).T))
            log_p = float(log_p)
        else:
            log_p = -np.inf
        return log_p

    # nBasis = basis.shape[1]
    # obs_dofs = self.human_dofs
    # noise = (self.noise_stdev ** 2) * np.identity(self.promp["nJoints"])
    # mu_w = mu_w[0:obs_dofs*nBasis, :]
    # sig_w = sig_w[0:obs_dofs * nBasis, 0:obs_dofs * nBasis]
    # H = self.observationMatrix(int(obs.shape[0]/alpha_sample),True)
    # A = H[0:obs_dofs,0:nBasis*obs_dofs]
    # mu_obs = np.matmul(A,mu_w)
    # sig_obs = np.matmul(A,np.matmul(sig_w,A.T)) + noise
    # obs_alpha_pdf = scipy.stats.multivariate_normal(mu_obs,sig_obs)

    def observationMatrix(self, k, only_obs=False):  # k = phase step, p = promp
        # Gn_d = p["basis"]["Gndot"]
        p = self.promp
        phaseStep = k
        nJoints = p["nJoints"]
        nTraj = p["nTraj"]
        Gn = p["basis"]
        nBasis = self.nBasis
        H = np.zeros((nJoints, nJoints * nBasis))
        if only_obs:
            for i in range(self.human_dofs):
                H[i, np.linspace(i, (i + nBasis - 1), (nBasis), dtype=int)] = Gn[(phaseStep - 1), :]
        else:
            for i in range(H.shape[0]):
                H[i, np.linspace(i, (i + nBasis - 1), (nBasis), dtype=int)] = Gn[(phaseStep - 1), :]
        return H


    def normalizeObservation(self, obs_data, alpha):
        human_dofs = self.human_dofs
        dt = self.dt
        ndata = np.empty((0, human_dofs))
        max_z = int(obs_data.shape[0] / alpha)
        for j in range(max_z):
            zj_time = j * alpha * dt
            corr_timestep = zj_time / dt
            whole = int(corr_timestep)
            frac = corr_timestep - whole
            data = []
            for k in range(human_dofs):
                if whole == (obs_data.shape[0] - 1):
                    data.append(obs_data[whole][k])
                else:
                    data.append(obs_data[whole][k] + frac * (obs_data[whole + 1][k] - obs_data[whole][k]))
            ndata = np.append(ndata, [data], axis=0)
        ndata = np.append(ndata, np.zeros((ndata.shape[0], self.robot_dofs)), axis=1)
        return ndata

    def conditionNormDist(self, obs_data, alpha, mu_new, cov_new):
        promp = self.promp
        sigma_obs = self.noise_stdev
        R_obs = (sigma_obs ** 2) * np.identity(promp["nJoints"])
        obs_index = range(obs_data.shape[0])
        for k in obs_index:
            H = self.observationMatrix(k,True)
            y0 = np.matrix(obs_data[k, :]).T

            # Conditioning
            tmp = np.matmul(H, np.matmul(cov_new, H.T)) + R_obs
            K = np.matmul(np.matmul(cov_new, H.T), np.linalg.inv(tmp))
            cov_new = cov_new - np.matmul(K, np.matmul(H, cov_new))
            mu_new = mu_new + np.matmul(K, (y0 - np.matmul(H, mu_new)))
            # For each observation, the mu_new is calculated from the mu_new of the last observation

        return mu_new, cov_new

    def weightsToTrajs(self, promp, wts):
        basis = promp["basis"]
        nDofs = promp["nJoints"]
        traj = np.zeros((basis.shape[0], nDofs))
        for i in range(nDofs):
            wi = wts[range(i * basis.shape[1], (i + 1) * basis.shape[1])]
            traj[:, i] = np.matmul(basis, wi).flatten()
        return traj

    def z2t(self, zdata, alpha):
        tmax = int(zdata.shape[0] * alpha)
        dt = self.dt
        nDofs = self.promp["nJoints"]
        data = np.zeros((tmax, self.promp["nJoints"]))

        for j in range(tmax):
            tj_time = j * dt
            corr_phasestep = tj_time / (alpha * dt)
            whole = int(corr_phasestep)
            frac = corr_phasestep - whole
            for k in range(nDofs):
                if whole == (zdata.shape[0] - 1):
                    data[j, k] = zdata[whole][k]
                else:
                    data[j, k] = zdata[whole][k] + frac * (zdata[(whole + 1), k] - zdata[whole, k])
        return data

    def plotTrajs(self, op_traj, expected_op):
        nDofs = self.promp["nJoints"]
        percerror = (np.abs(((expected_op.shape[0]) - (op_traj.shape[0]))) / (expected_op.shape[0] - 1)) * 100
        print("Percentage Error in Time", percerror)

        fig, axs = plt.subplots(2)
        fig.tight_layout(pad=2)
        # plt.figure(1)
        axs[0].set_title("Human Trajectory")
        axs[0].plot(expected_op[:, 0], expected_op[:, 1], label="True")
        axs[0].plot(op_traj[:, 0], op_traj[:, 1], label="Prediction")
        axs[0].set(xlabel="X position",ylabel="Y position")
        axs[0].legend()

        axs[1].set_title("Robot Trajectory")
        axs[1].plot(expected_op[:, 2], expected_op[:, 3], label="True")
        axs[1].plot(op_traj[:, 2], op_traj[:, 3], label="Prediction")
        axs[1].set(xlabel="X position", ylabel="Y position")
        axs[1].legend()

        # plt.figure(3)
        # plt.title("Human x")
        # plt.plot(expected_op[:, 0], label="True")
        # plt.plot(op_traj[:, 0], label="Prediction")
        # plt.legend()
        #
        # plt.figure(4)
        # plt.title("Human y")
        # plt.plot(expected_op[:, 1], label="True")
        # plt.plot(op_traj[:, 1], label="Prediction")
        # plt.legend()
        #
        # plt.figure(5)
        # plt.title("Robot x")
        # plt.plot(expected_op[:, 2], label="True")
        # plt.plot(op_traj[:, 2], label="Prediction")
        # plt.legend()
        #
        # plt.figure(6)
        # plt.title("Robot y")
        # plt.plot(expected_op[:, 3], label="True")
        # plt.plot(op_traj[:, 3], label="Prediction")
        # plt.legend()

        plt.show()

    def resetProMP(self):
        self.mu_new = self.promp["w"]["mean_full"]
        self.cov_new = self.promp["w"]["cov_full"]
        self.obsdata = np.empty((0, (self.promp["nJoints"])))
        # self.obsndata = np.empty((0, (self.promp["nJoints"])))


def printarr(arr, name="None"):  # This function is only for debugging purposes
    print("VariableName: ", name)
    for i in range(arr.shape[0]):
        print(arr[i, :])
def comparePlots(ip_traj, op_traj):  # This function is only for debugging purposes

    plt.figure(1)
    plt.plot(ip_traj[:, 0], ip_traj[:, 1])
    plt.show()
    plt.plot(op_traj[:, 0], op_traj[:, 1])
    plt.show()

    # plt.figure(2)
    # plt.plot(ip_traj[:, 2], ip_traj[:, 3])
    # plt.plot(op_traj[:, 2], op_traj[:, 3])


def main(args):
    # TODO: Allow sequential observations
    pmp = ProMP(ndemos=45, hum_dofs=2, robot_dofs=2, dt=0.1, training_address="Data\Human A Robot B 1")
    # To give different inputs change the parameters passed to the constructor above.
    # ndemos = No. of demos, hum_dofs = master dofs, robot_dofs = slave dofs, dt = delta t between 2 position measurements in a demo
    # training_address = path of the folder in which your data is present
    # Also to be changed: In loadData line 44 and 45, change the name of your master data and slave data file name (without the demo number).
    # Default master data file name: letterAtr followed by demo number.
    # Default slave data file name: letterBtr followed by demo number.
    testdemo = 49
    test_data = np.loadtxt(open("Data\Human A Robot B 1\letterAtr"+str(testdemo)+".csv"), delimiter=",")
    test_data_robot = np.loadtxt(open("Data\Human A Robot B 1\letterBtr"+str(testdemo)+".csv"), delimiter=",")
    ip_traj = np.concatenate((test_data,test_data_robot),axis=1)
    num_pts = int(0.5*test_data.shape[0])  # Enter the number of points you want in your input
    test_data = np.delete(test_data, np.linspace(num_pts, (len(test_data) - 1), (len(test_data) - num_pts), dtype=int),axis=0)  # Trimming data
    test_data = np.append(test_data, np.zeros((test_data.shape[0], 2)), axis=1)
    true_alpha = ip_traj.shape[0]/123.37
    # Expected observation data format: [col(obs of human dof1),col(obs of human dof2),...,col(obs of last human dof), (columns of zeros for each robot dof)]
    # for i in range(test_data.shape[0]):
    #     indata = test_data[i,:].reshape(1,4)
    traj = pmp.predict(test_data,true_alpha)

    print("\nPrediction Executed Successfully \nPlotting...")
    # If you want to use sequential observation data, at each time step, obtain the observation in the "expected format" (line 394) with a single row
    # and pass it in pmp.predict as test_data.

    # Now to plot the results
    pmp.plotTrajs(traj,ip_traj)
    pmp.resetProMP()

if __name__ == '__main__':
    main(sys.argv)







# Commands for test variables:
# test1 = [np.round(np.random.rand(3,2)*10),np.round(np.random.rand(3,2)*10)]
# test2 = []
# test2.append(test1[0][:,0].T)
# test2.append(test1[1][:,0].T)
# a = np.loadtxt(open('Data\Human A Robot B\letterAtr2.csv'),delimiter=",")
# A.append(a)
# A.append(a)

