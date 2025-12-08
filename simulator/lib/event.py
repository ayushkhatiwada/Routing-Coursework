"""
    The Event class which represents an event to occur in the
    simulator.
"""
class Event:
    """
        Event constructor, which takes the name of the event,
        the time the event is to occur, and a list of arguments to the event.
    """
    def __init__(self, o, t, a):
        self._operation = o
        self._time = t
        self._args = a
        self._done = False

    """
        Return the time this event is scheduled to occur.
    """
    def getTime(self):
       return self._time

    """
        Get the operation set by this event.
    """
    def getOperation(self):
       return self._operation

    """
        Get the number of arguments this event has.
    """
    def getNumberOfArguments(self): 
       return len(self._args)

    """
        Return argument i to the event which was set in the config file.
    """
    def getArgument(self, i):
       return self._args[i]

    """
        Generic toString method which describes the event and its arguments.
    """ 
    def __str__(self):
        s = "Event \'{0}\' occurring at time {1}".format(self._operation, self._time)
        if len(self._args) > 0:
            s += " with parameters {}".format(self._args)
        return s

    """
        Sets the event as done.
    """
    def setDone(self):
       self._done = True

    """
        Gets whether the event has occured or not.
    """
    def getState(self):
        return self._done
