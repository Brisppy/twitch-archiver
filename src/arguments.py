class Arguments:
    """
    Function for parsing arguments for access later.
    """
    __args = {}

    @staticmethod
    def setup_args(args):
        """Sets up and formats provided arguments.

        :param args: arguments object to create parameters from
        """
        for argument in args:
            Arguments.set(argument, args[argument])

        if not Arguments.get('chat') and not Arguments.get('video'):
            Arguments.set('chat', True)
            Arguments.set('video', True)

        if Arguments.get('vod_id'):
            Arguments.set('vod_id', [vod_id for vod_id in Arguments.get('vod_id').split(',')])

        elif Arguments.get('channel'):
            Arguments.set('channel', [channel for channel in Arguments.get('channel').split(',')])

    @staticmethod
    def set(name, value):
        """Set a specified class attribute.

        :param name: name of attribute to change
        :param value: value to set attribute to
        """
        Arguments.__args[name] = value

    @staticmethod
    def get(name=None):
        """Retrieve a specified attribute.

        :param name: name of attribute to retrieve value of or none to return all
        :return: value of requested attribute, or all attributes if none provided
        """
        if name is None:
            return Arguments.__args

        return Arguments.__args[name]
