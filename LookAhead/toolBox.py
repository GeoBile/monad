"""
Copyright 2015 Ericsson AB

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the 
specific language governing permissions and limitations under the License.
"""
import mutation
import inits
from deap import base
from deap import creator
from deap import tools
from scoop import futures
from dbConnection import DB
from fitness import Fitness
from operator import itemgetter
import datetime
from datetime import timedelta



# Constant
BUS_LINE = 2
DB.noOfslices = 0
# The individual size corresponds to the number of trips
INDIVIDUAL_SIZE =  14
INDIVIDUAL_SIZE_BOUNDS = [30, 90]


# Initialize the classes
databaseClass = DB()
fitnessClass = Fitness()
def generateStartTimeBasedOnFreq(busLine,frequency, startTime):
    # we make sure the starting time is in between the upper and lower bound of our time slices
    startTimeArray = []
    lineTimes = {}
    for x in DB.timeSliceArray:
        start = datetime.datetime.combine(Fitness.yesterday, datetime.time(x[0], 0, 0))
        end = datetime.datetime.combine(Fitness.yesterday, datetime.time(x[1], 59, 59))

        # if the startTime is in a specific time slice
        if start <= startTime <= end:
            NextstartTime = startTime + datetime.timedelta(minutes=frequency)
            NextstartTime2 = startTime - datetime.timedelta(minutes=frequency)
            startTimeArray.append(startTime)
            if NextstartTime <= end:
                startTimeArray.append(NextstartTime)
            if NextstartTime2 >= start:
                startTimeArray.append(NextstartTime2)

            while NextstartTime <= end:

                NextstartTime = NextstartTime + datetime.timedelta(minutes=frequency)
                if NextstartTime <= end:
                    startTimeArray.append(NextstartTime)

            while NextstartTime2 >= start:

                NextstartTime2 = NextstartTime2 - datetime.timedelta(minutes=frequency)

                if NextstartTime2 >= start:
                    startTimeArray.append(NextstartTime2)

    return sorted(startTimeArray) 

def genTimetable(individual):

    busLines = [x[0] for x in individual]
    busLines[:] = set(busLines)
    times = {}
    for line in busLines:
        ind = [x for x in individual if x[0] == line]
        for i, val in enumerate(ind):
            generate = generateStartTimeBasedOnFreq(line,val[2], val[3])
            if line not in times:
                times[line] = generate
            else:
                times[line] = times[line] + generate
                #print "Result starting times....."


    print "best individual"
    print individual
    print "times..................."
    #print sorted(times.items(), key = lambda e: e[0])
    print times[2]
    print times[102]



def evaluateNewIndividualFormat(individual):
    individual = sorted(individual, key=itemgetter(3))
    individual = sorted(individual, key=itemgetter(0))
    #print "Individual................."
    #print individual
    
    # Second, we loop trough the number of genes in order to retrieve the
    # number of requests for that particular trip
    # For the 1st trip, the starting time has to be selected
    request = []
    totalWaitingMinutes = []
    cnt = []
    initialTripTime = datetime.datetime.combine(fitnessClass.yesterday, 
                                       datetime.datetime.strptime("00:00", 
                                       fitnessClass.formatTime).time())
    db = DB()
    # ----------------------------------------------------
    # Evaluate average time based on requests (& capacity)
    # ----------------------------------------------------
    leftOver = []

    for i in range(len(individual)):
        phenotype = db.generatePhenotype(individual[i][0], individual[i][3])
        initialCrew = 0
        leftOvers = 0
        leftOversWaitTime = 0
        sliceLength = (db.timeSliceArray[0][1] - db.timeSliceArray[0][0]) + 1
        noOfTrips = sliceLength*60/individual[i][2]

        for j in range(len(phenotype)):
            # TODO: Fix trips that finish at the next day
            initialTrip = initialTripTime
            lastTrip = phenotype[j][1]
            if initialTrip > lastTrip:
                initialTrip = lastTrip - timedelta(minutes=db.getFrequency(individual[i][0]))
            # Search on Fitness.request array for the particular requests
            #request = fitnessClass.searchRequest(initialTrip, lastTrip, phenotype[j][0], individual[i][0])
            request, count = fitnessClass.search(initialTrip, lastTrip, phenotype[j][0], individual[i][0])

            #requestOut = fitnessClass.searchRequestOut(initialTrip, lastTrip, phenotype[j][0], individual[i][0])
            # TODO: Replace the length by the sum of the number of requests
            #initialCrew = initialCrew + (len(request) - len(requestOut))
            initialCrew = initialCrew + count 
            totalRequests = 0
            if(initialCrew > noOfTrips * individual[i][1]):
                # People that did not make it !!
                leftOvers = initialCrew - noOfTrips * individual[i][1]
                # Total time = number of people times waiting time in minutes
                if i < len(phenotype)-1: # wth is this?
                    leftOversWaitTime = leftOvers * fitnessClass.getMinutesNextTrip(db.generatePhenotype(individual[i+1][0], individual[i+1][3]), lastTrip, phenotype[j][0])
                else:
                    # Heuristic, computation of this would result really expensive
                    leftOversWaitTime = leftOvers * db.minutesHour
            initialTripTime = phenotype[j][1]
            if len(request) > 0:
                waitingMinutes = 0
                count = 0
                for k in range(len(request)):
                    waitingTime = phenotype[j][1] - request[k]["_id"]["RequestTime"]
                    waitingMinutes = waitingMinutes + (waitingTime.days * databaseClass.minutesDay) + (waitingTime.seconds / databaseClass.minutesHour)
                    count = count + int(request[k]["total"])
                totalWaitingMinutes.append(waitingMinutes)
                cnt.append(count)

    totalLeftOverTime = 0
    for k in range(len(leftOver)):
        totalLeftOverTime += leftOver[k][1]
    totalWaitingTime = sum(totalWaitingMinutes) + totalLeftOverTime
    # totalWaitingTime = sum(totalWaitingMinutes) + tripWaitingTime.total_seconds()/60.0
    # averageWaitingTime = totalWaitingTime / (sum(cnt) + noOfLeftOvers)
    return fitnessClass.calculateCost(individual, totalWaitingTime, 0),


def evalIndividual(individual):
    ''' Evaluate an individual in the population. Based on how close the
    average bus request time is to the actual bus trip time.

    @param an individual in the population
    @return a summation of the difference between past past requests'
    average trip starting time and actual start time
    according to the evolving timetable.
    Lower values are better.
    '''
    # First, the randomly-generated starting times are sorted in order to
    # check sequentially the number of requests for that particular trip
    individual = sorted(individual, key=itemgetter(2))
    # Second, we loop trough the number of genes in order to retrieve the
    # number of requests for that particular trip
    # For the 1st trip, the starting time has to be selected
    request = []
    totalWaitingMinutes = []
    cnt = []
    initialTripTime = datetime.datetime.combine(fitnessClass.yesterday, 
                                       datetime.datetime.strptime("00:00", 
                                       fitnessClass.formatTime).time())
    db = DB()
    # ----------------------------------------------------
    # Evaluate average time based on requests (& capacity)
    # ----------------------------------------------------
    leftOver = []
    for i in range(len(individual)):
        phenotype = db.generatePhenotype(individual[i][0], individual[i][2])
        initialCrew = 0
        leftOvers = 0
        leftOversWaitTime = 0
        for j in range(len(phenotype)):
            # TODO: Fix trips that finish at the next day
            initialTrip = initialTripTime
            lastTrip = phenotype[j][1]
            if initialTrip > lastTrip:
                initialTrip = lastTrip - timedelta(minutes=db.getFrequency(individual[i][0]))
            # Search on Fitness.request array for the particular requests
            request = fitnessClass.searchRequest(initialTrip, lastTrip, phenotype[j][0], individual[i][0])
            requestOut = fitnessClass.searchRequestOut(initialTrip, lastTrip, phenotype[j][0], individual[i][0])
            # TODO: Replace the length by the sum of the number of requests
            initialCrew = initialCrew + (len(request) - len(requestOut))
            if(initialCrew > individual[i][1]):
                # People that did not make it !!
                leftOvers = initialCrew - individual[i][1]
                # Total time = number of people times waiting time in minutes
                if i < len(phenotype)-1:
                    leftOversWaitTime = leftOvers * fitnessClass.getMinutesNextTrip(db.generatePhenotype(individual[i+1][0], individual[i+1][2]), lastTrip, phenotype[j][0])
                else:
                    # Heuristic, computation of this would result really expensive
                    leftOversWaitTime = leftOvers * db.minutesHour
                leftOver.append([leftOvers,leftOversWaitTime])
            initialTripTime = phenotype[j][1]
            if len(request) > 0:
                waitingMinutes = 0
                count = 0
                for k in range(len(request)):
                    waitingTime = phenotype[j][1] - request[k]["_id"]["RequestTime"]
                    waitingMinutes = waitingMinutes + (waitingTime.days * databaseClass.minutesDay) + (waitingTime.seconds / databaseClass.minutesHour)
                    count = count + int(request[k]["total"])
                totalWaitingMinutes.append(waitingMinutes)
                cnt.append(count)

    totalLeftOverTime = 0
    for k in range(len(leftOver)):
        totalLeftOverTime += leftOver[k][1]
    totalWaitingTime = sum(totalWaitingMinutes) + totalLeftOverTime
    # totalWaitingTime = sum(totalWaitingMinutes) + tripWaitingTime.total_seconds()/60.0
    # averageWaitingTime = totalWaitingTime / (sum(cnt) + noOfLeftOvers)
    return fitnessClass.calculateCost(individual, totalWaitingTime, 0),


# Creating a minimizing fitness class to minimize a single objective that
# inherits from the base class "Fitness".
creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
# Creating an individual class that inherits a list property and has a fitness
# attribute of type FitnessMin
creator.create("Individual", list, fitness=creator.FitnessMin)

# Initialize the toolbox from the base class
toolbox = base.Toolbox()

# Register the operations to be used in the toolbox
toolbox.register("attribute", databaseClass.generateRandomStartingTimeForTrip)
toolbox.register("individual", tools.initRepeat, creator.Individual,
                 toolbox.attribute, INDIVIDUAL_SIZE)
#toolbox.register("individual", inits.initRepeatBound, creator.Individual,
#                  toolbox.attribute, INDIVIDUAL_SIZE_BOUNDS)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("evaluate", evaluateNewIndividualFormat)
toolbox.register("mate", tools.cxOnePoint)
toolbox.register("select", tools.selTournament, tournsize=3)
toolbox.register("mutate", mutation.mutUniformTime)
toolbox.register("map", futures.map)
