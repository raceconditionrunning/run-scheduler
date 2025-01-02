# run-scheduler

An [Answer Set Programming](https://en.wikipedia.org/wiki/Answer_set_programming) domain for setting a club long-run schedule. Derived from our [relay scheduler](https://github.com/raceconditionrunning/relay-scheduler).

* Schedules from scratch 
* ...or give a sketch and have the solver fill in the rest
* Consumes routes in GeoJSON format


## Usage

Get a working installation of [Clingo](https://github.com/potassco/clingo) >=5.5. Potassco's Anaconda channel makes this easy, or you can make a virtual env and install from requirements.txt

For Apple Silicon Macs, use Homebrew and ensure you install cffi in the correct version of Python, e.g. `python3.12 -m pip install cffi`.

You need a fully built copy of the [Race Condition Running website](https://github.com/raceconditionrunning/raceconditionrunning.github.io), which includes tables of routes and locations.

Specify your problem matching the format used in any of the `schedules/*.lp`. 

Now, using the correct paths for the routes and locations files/directories:

    ./solve.py 25_winter routes.yml routes/geojson/ locations.geojson 

Solutions will stream into a timestamped folder in `solutions/`. By default, all optimal solutions are saved.

Use `--help` to see additional options.

Note that the solver will process float terms by converting them to a fixed precision (two decimal places, by default).

To view a solution, use 
    
        ./print_schedule.py solutions/<run>/solution.json
