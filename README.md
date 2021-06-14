# Inevitable Zero

A mod for *Trails from Zero* that ports over the PS Vita-exclusive quests to the
PC version. Works with the original Japanese release and Geofront *version 1.0.2
only*. The translation is a work in progress.

<details><summary>Ultimate Bread Showdown!</summary>
In chapter 2, first day, after returning from Armorica Village.

The result is announced in chapter 3, second day.

For this one I also rename «Luscious Orange» to «Zesty Orange», because
I couldn't find any other way to get the translation to make sense.
</details>
<details><summary>Search for the Oversleeping Doctor</summary>
Chapter 2, second day.

After talking to Azel, he disappears until you leave and come back. I don't know
if this is how it works in the Vita version or if it's a bug in this patch.
</details>
<details><summary>Search for a Certain Person</summary>
Chapter 3, fifth day.
</details>
<details><summary>Clerk’s Customer Service Guidance</summary>
Start of chapter 4.
</details>
<details><summary>Guest Lecturer for Sunday School (Continued)</summary>
Start of chapter 4.
</details>

I haven't figured out if it's possible to change the detective rank milestones,
so since this mod adds a total of 14 extra DP, those are somewhat easier to
reach.

It also contains a small number of other patches:

<details><summary>Some exclamations from Fran when she calls</summary>
When asking the gang to find Colin, and after exploring the Moon Temple.
</details>
<details><summary>One small line during a discussion with Sergei, which solves a minor plot hole (spoilers!)</summary>
When discussing the D∴G Cult, Sergei writes down how it is spelled.
</details>
<details><summary>A small bugfix in Geofront's patch (which might have been fixed in recent versions)</summary>
When Jona calls for the first time, it seems the delayed dialogue line
might have screwed some things up.
</details>

## Usage

`python patch.py --help`  
`python dump.py --help`


## Compatibility

The scripts can currently only patch against vanilla and Geofront version 1.0.2,
due to a recent change in their patching infrastructure which makes it difficult
to decompile. The patched scripts work if you install them over a more recent
Geofront, though of course this reverts some of their changes.
