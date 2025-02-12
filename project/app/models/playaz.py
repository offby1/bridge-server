from faker.providers.person import Provider


class WireCharacterProvider(Provider):
    first_names = (
        "Alma",
        "Asst. Princip. Donnely",
        "Avon",
        "Beadie",
        "Bird",
        "Bodie",
        "Brianna",
        "Brother Mouzone",
        "Bubbles",
        "Bunk",
        "Bunny",
        "Burrell",
        "Butchie",
        "Carcetti",
        "Carver",
        "Cheese",
        "Chris",
        "Cutty",
        "D'Angelo",
        "Daniels",
        "Del. Watkins",
        "Det. Norris",
        "Donette",
        "Donut",
        "Double G",
        "Dukie",
        "Frank",
        "Freamon",
        "Gus",
        "Herc",
        "Holley",
        "Horseface",
        "Judge Phelan",
        "Kima",
        "Klebanow",
        "Landsman",
        "Levy",
        "Little Man",
        "Marla",
        "Marlo",
        "Mayor Royce",
        "McNulty",
        "Michael",
        "Namond",
        "Nick",
        "Norman",
        "Omar",
        "Polk",
        "Poot",
        "Prez",
        "Prop Joe",
        "Randy",
        "Rawls",
        "Rhonda",
        "Santangelo",
        "Scott",
        "Sen. Davis",
        "Shardene",
        "Slim Charles",
        "Snoop",
        "Stinkum",
        "Stringer",
        "Sydnor",
        "The Greek",
        "Tilghman",
        "Tony Gray",
        "Valchek",
        "Vondas",
        "Wallace",
        "Walon",
        "Wee-Bey",
        "White Mike",
        "Ziggy",
        "Zorzi",
    )

    def playa(self):
        return self.random_element(self.first_names)
