## [Unreleased] - yyyy-mm-dd

### Added
- Closes #68, adds ability to select base price from buy, sell or split prices.
- Added help icons and explanations for item sheet

### Changed

### Fixed
- Fixed mistake in displaying total raw values for refined ore in calculation sheets.

## [1.12.2] - 2023-11-25

### Added
- Closes #69, A0 ores as refinable ores

### Fixed
- Fixes #70, typo in contract settings

## [1.12.1] - 2023-08-08

If you are on a fresh insall since 1.12 and are having issues with prices generating for program (red hands and question marks) run the data load command `python manage.py buybackprogram_load_data` after installing this patch to get the missing market groups.

### Fixed
- Fixes #66, adds Rogue Drone Infestation Data to red loot table
- Fixes #67, Fixes market groups missing for new installs that caused items to be disallowed.

## [1.12.0] - 2023-07-23

### Added
- Minimum eveuniverse version bump django-eveuniverse>=1.0.0

### Changed
- Improve eveuniverse data load

### Fixed
- Fixed issue #62, contracts failing to fetch if a token is invalid

# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [1.11.1] - 2023-04-18

### Fixed
- Fixes #60, contracts with titles that include extra character no longer gets marked as untracked

## [1.11.0] - 2023-04-16

### Added
- Closes #61, added an option for programs to display or hide the contract item list on discord messages.

## [1.10.0] - 2023-04-10

### Added
- Closes #57, Added more details for discord messages

### Fixed
- Fixed issue #58, changed contract IDs to unique

## [1.9.1] - 2023-03-29

### Added

- Test factories for all models
- Test data for eveuniverse models
- Tests for Owner

### Fixed

- Memory leak in Owner._get_location_name()
- Update contracts breaks with new eve types

## [1.9.0] - 2023-03-27

No breaking changes in the update. Migrations needed.

### Added

- Added a new setting `BUYBACKPROGRAM_TRACK_PREFILL_CONTRACTS` that will determine if we will check all contracts from owners that include the buyback prefill. This is used to catch possible scam contracts trying to mimic as valid buyback contracts.
- Added a new setting `BUYBACKPROGRAM_UNUSED_TRACKING_PURGE_LIMIT` that will determine how long unlinked tracking objects (with no corresponding contracts) will be stored until purged
- Added a maintenance task within the price_update tasks which will remove tracking objects that are not linked to any contracts

### Changed

- Increased tracking number max characters to 32
- Updated pre-commit

### Fixed

- Fixed #54, a running id key is now added to tracking numbers to make then unique.

## [1.8.5] - 03-12-2023

### Fixed

- Fixed performance table issues
- Fixed #52 - Too long location names caused issues when creating new locations
- Fixed #53 - Contracts not updating if manager has no docking access to station

## [1.8.3] - 06-11-2022

### Added

- Readme for location scope

## [1.8.2] - 06-11-2022

### Changed

- Fixes #50, Changed contract actual location name to be stored in database. Contract locations will only be displayed to contracts fetched in version 1.8.2

## [1.8.1] - 06-11-2022

### Added

- Added location name information for tracking by [Arc Tiru](https://gitlab.com/arctiru)

### Fixed

- Fixes #49, fixes issue where missing items when using Janice API caused price update to crash

### Removed

- Dropped support for python 3.7
- Dropped support for AA 2.x

## [1.8.0] - 20-09-2022

This update adds beter statistics and leaderboard for each program. Users will be able to display the leaderboard for each program they are able to see if they have been granted the view_leaderboard setting. Leaderboard displays a datatable for each month total isk and total donations count.

Performance table tracks the performance of each individual program and is visible for the program owners and to users who have the see_performance permission.

### Added

- Added new permission: `see_leaderboard`
- Added new permission: `see_performance`
- Added leaderboard and performance statistics for programs (Thanks [Arc Tiru](https://gitlab.com/arctiru))
- Adds new CSS files for light and dark themes

### Changed

- Changed program refining rate to allow 2 decimals

### Fixed

- Fixed type in css file name
- Fixed type in readme on Janice name

## [1.7.0] - 09-09-2022

### Added

- Added ability to select Janice API as the price source
- Added ability to adjust contract expire date

## [1.6.4] - 24-07-2022

### Changed

- Changed item not found message to be more accurate for cases with unpacked renamed items
- Changed missing item images to a static image

### Fixed

- Fixed an message error when deleting a program.

## [1.6.3] - 27-06-2022

### Fixed

- Fixed an issue that occured when a user tried to sell a mission ore while the program had compressed or refined value accepted causing the program to crash with error 500

### Changed

- Changed the notification for unpublished items to indicate where the item is unpublished or a special commondite item without any market categories such as a mission item.

## [1.6.2] - 24-05-2022

### Added

- Closes #45, Added notes for contract tracking to indicate unmatching items or quantities

## [1.6.1] - 23-06-2022

### Added

- Added notification for missing NPC prices in database
- Added notification for outdated prices
- Added setting `BUYBACKPROGRAM_PRICE_AGE_WARNING_LIMIT`to detemine the warning limit in hours for outdated prices. Default 48 hours
- Included NPC prices into the price preload command `python manage.py buybackprogram_load_prices`

### Fixed

- Fixed error when NPC price was used but no NPC price had been loaded in database
- Fixed Jita prices not updating when debug mode was in use

## [1.6.0] - 19-06-2022

This release requires migrations. Add a discord webhook to a program to receive notifications about new contracts.

This release includes updates that make buybackprogram notifications work with the current latest versions of aa-discordbot and discordproxy. These programs require minimum Python Version 3.8 to work and the New Discord Lib Py-Cord. If you are still running on the old versions the notifications will not work for you but everything else will.

### Added

- Closes #43, added NPC value option for CCS bonds.
- Closes #41

### Changed

- Changed channel notifications to use webhooks instead of discord bots.
- Changed DM messages as embeds for discordbot

### Fixed

- Fixed #42, Talassonite not behaving as an ore
- Fixed #44, Added support to latest aa-discordbot and discordproxy

## [1.5.6] - 2022-05-26

### Fixed

- Fixed an issue where channel notifications were not sent if discordnotify app was installed

## [1.5.5] - 2022-05-22

### Fixed

- Fixed an issue where unpacked item caused an error when sold via a program that had a positive value in the JF fuel cost field.

## [1.5.4] - 2022-05-21

If you want to change where you pull your base prices from (Jita as default) you can do this by changing the values of `BUYBACKPROGRAM_PRICE_SOURCE_NAME` and `BUYBACKPROGRAM_PRICE_SOURCE_ID`. You can also change the source with an old install of this app simply by adjusting the values of these fields and running the price updates again.

### Added the ability to select another price sources beside Jita

## [1.5.3] - 2022-05-21

### Added

- Added type hints to urls

### Changed

- Dropped support for python 3.6

### Fixed

- Fixes #40, expired contracts were showing as outstanding
- Fixes #39, compressed volume was not used for fuel calculations

## [1.5.2] - 2022-04-21

### Added

- Added combability for AA3/Django4

## [1.5.1] - 2022-04-09

### Fidex

- Fixed #38, error when item was in invalid state

## [1.5.0] - 2022-04-06

### Fixed

- Fixes #37, added option to ignore price dencity for compressable items. This is mainly to counter the low buy orders for compressed moon ore in current release.

## [1.4.1] - 2022-04-03

This version changes how ore price variant density tax is calculated. Prior to this version the price density for the best price variant was caulculated based on the attributes for the best price variant. Ie. Some moon ores would inherit partial increased taxes as their minerals in the refined price variant could have low price density. After this patch all items that can be compressed get their price density based on the compressed variant no matter what settings are used. Items that can't be compressed use always the raw item value for this calculation.

### Changed

- Fixes #36, Changed how price density is calculated on ore variant prices. Now using compression value for ore, raw for everything else.

### Fixed

- Removed comparison price (that was not displayed anywhere) to remove errors when jita buy price is 0
- Fixes #33, fixed faulty notification for incorrect price when donation was set to 100%
- Fixed locations not displaying correctly on contract details page
- Fixed #32, Fixed updated message on editing a program
- Fixes #35, our buy price displayed an incorrect value when refined price method was used. Had no effect on net value.
- Fixed raw value jita buy column showing jita sell price

## [1.4.0b] - 2022-04-02

This version changes how ore price variant density tax is calculated. Prior to this version the price density for the best price variant was caulculated based on the attributes for the best price variant. Ie. Some moon ores would inherit partial increased taxes as their minerals in the refined price variant could have low price density. After this patch all items that can be compressed get their price density based on the compressed variant no matter what settings are used. Items that can't be compressed use always the raw item value for this calculation.

### Changed

- Fixes #36, Changed how price density is calculated on ore variant prices. Now using compression value for ore, raw for everything else.

### Fixed

- Fixes #33, fixed faulty notification for incorrect price when donation was set to 100%
- Fixed locations not displaying correctly on contract details page
- Fixed #32, Fixed updated message on editing a program
- Fixes #35, our buy price displayed an incorrect value when refined price method was used. Had no effect on net value.
- Fixed raw value jita buy column showing jita sell price

## [1.3.0] - 2022-02-24

### Added

- Added the ability to select multiple buy locations for one program. Closes #29

### Changed

- Changed displayed tax amount to 2 digitals
- Changed tracking created at time to be timezone aware

### Fixed

- Removed dublicated item tax icons from ores that used refined price as best price and had an item adjusted tax set on them. Now only displaying one icon.
- Fixed #31, removed a tem debug line left over from development

## Updating

- This version requires database migrations.
- After updating make sure you re-add the accepted locations for your programs.

## [1.2.8] - 2022-03-20

### Added

- Added repo url to setup.py
- Icon for raw price used when item has price variants

### Changed

- Limited price density displayed decimals to 2

### Fixed

- Fixed an issue where moon ores were accepted as raw ores even when raw ore valuation was disabled
- Fixed raw moon ore price not displayed when program had raw values set to true

## [1.2.7] - 2022-05-08

### Changed

- Changed ore, ice and moon ore compression rate to 1:1 to reflect changes in eve patch 20.03

### Notes

- Remember to update static files with `buybackprogram_load_data` to fetch the new compression types

## [1.2.6] - 2022-05-03

### Fixed

- AA3x / Django4 compatibility

## [1.2.5] - 2022-02-01

### Fixed

- Fixed the issue where channel notifications did not work with aa-discordbot

## [1.2.4] - 2022-01-29

### Fixed

- Fixed the issue where item check gave false positives when the seller had multiple items with same names and different quantities sold

## [1.2.3] - 2022-01-26

### Fixed

- Added missing order from item match checker that could sometimes cause false positives for missing items.

## [1.2.2] - 2022-01-26

### Added

- Added checks for new contracts to see if the calculated items match the actual items in the contract

### Changed

- Changed contraact details to order both invoiced and contract items the same way

## [1.2.1] - 2022-01-26

### Fixed

- Fixes #27, added command buybackprogram_link_contracts to link up old contracts prior to 1.2.0 on statics pages

## [1.2.0] - 2022-01-26

### Added

- Added ForeignKey to tracking objects to link them with actual contracts
- Added datetime field for tracking objects for creation time
- Closes #26, added name/description field for programs
- Closes #23, added program location row to contract details

### Changed

- Performace increase for databses with a lot of tracking objects to the statistics pages

### Fixed

## [1.1.1] - 2022-01-24

### Changed

- Changed notification layouts for discordproxy

### Fixed

- Fixed contracts showing donation icons only if contract had no donations.
- Fixees #25, fixed issue with notifications when an alt corp was used as manager
- Fixed rejected notifications not going out to sellers

## [1.1.0] - 2022-01-22

### Added

- Added check for discordnotify app to prevent multiple notifications
- Improvent error hanlding on when discordproxy was installed but not running

### Changed

- Reconstructed how notifications work. Greatly improved speed for statistics pages.

### Fixed

- Fixes #24
- Fixes #22

## [1.0.2] - yyyy-mm-dd

### Added

- Closes #21, added parent group mentions for market group item tax fields

### Changed

### Fixed

- Item tax not applying on price variants correctly
- Fixes #20, allow to set 0% item taxes

## [1.0.1] - yyyy-mm-dd

### Fixed

- Fixes #18, compressed variant not used on already compressed ores
- Fixes #19, fixes view all statistics permission issue

## [1.0.0] - 2022-01-09

**THIS RELEASE CONTAINS MAJOR CHANGES THAT REQUIRE A CLEAN REINSTALL OF THE APP. ALL PREVIOUS DATA INSIDE THIS APP WILL BE LOST**

## Updating from 0.1.8 to 1.0.0

- Activate your virtual enviroment `source /home/allianceserver/venv/auth/bin/activate`
- Remove all data from 0.1.8 **THIS COMMAND WILL REMOVE ALL DATA FROM THE BUYBACKPROGRAM APP STORED IN YOUR DATABASE** `python /home/allianceserver/myauth/manage.py migrate buybackprogram zero`
- Upgrade to 1.0.0 with `pip install -U aa-buybackprogram==1.0.0`
- Run the migrations `python /home/allianceserver/myauth/manage.py migrate`
- Collect static files `python /home/allianceserver/myauth/manage.py collectstatic`
- Restart auth `supervisorctl restart myauth:`
- Load data `python manage.py buybackprogram_load_data`
- Load prices `python manage.py buybackprogram_load_prices`
- Setup your programs

### Added

- Fixed #10, added ability to delete own locations
- Fixes #9, added ability to track contract locations per structure ID
- Fixes #13, added ability to praisal blue and red loot by npc buy orders
- Fixes #5, added the ability to receive notifications for new contracts and for sellers notifications about completed contracts, supports both aa-discordbot and discordproxy.
- Fixed #15, added mention of scopes into readme file
- Fixes #12, added requirement for eveuniverse in readme
- Fixes #8, added the ability to add special taxes via market groups
- Added total refined value row for refined prices

### Changed

- Fixes #11, now also tracking contracts that have extra characters in the description such as extra spaces.
- Merger readme periodic tasks into a single code block to make copying easier
- Removed ability to use locations that were created by other managers.
- Moved some views into a separate file
- Added more views for special taxes
- Renamed special taxes view paths

### Fixed

- Fixed #16, a corporation can now have multiple managers

## [0.1.8] - 2021-12-24

### Fixed

- Availability field not displaying corp if owner is a corporation on calculation page
- Fixes #7, refined price not used correctly when selling compressed price with only refined pricing method.
- Fixed wrong crontab settigs for contract updates
- Readme spelling fixes

## [0.1.6] - 2021-12-24

### Fixed

- Calculation quantities did not parse correctly if the user had hidden or added more columns to the default detailed view.

## [0.1.5] - 2021-12-24

### Fixed

- Fixed #3
- Fixes #4 by adding support for UK localization

## [0.1.4] - 2021-12-24

### Changed

- Contract celery schedule to every 15 minutes

### Fixed

- #4 Localization issues with number formats

### Fixed

- Readme styling

## [0.1.3] - 2021-12-23

### Added

- Missing manifest entry for swagger.json

## [0.1.2] - 2021-12-23

### Changed

- Tracking item creation changed to bulk create to decrease database calls

### Fixed

- Multiple typos

## [Unreleased] - yyyy-mm-dd

### Added

### Changed

### Fixed
